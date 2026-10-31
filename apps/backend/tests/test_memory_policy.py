"""M4-S1 container-free tests: the provider gate, content minimization, strict request shapes and the fail-closed route seam."""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from database.pg import get_pg_session
from memory import policy
from memory.service import MemoryRejected
from routes.memory_routes import memory_customer, router
from schemas.memory_schema import ConsentRequest, MemoryCreate, MemoryUpdate

DECLARED = "acme=no_training,selfhost=self_hosted,optout=opt_out,trainer=may_train,typo=no-training"
FREE = "groq,gemini,openrouter"
IDEM = "idem_0123456789abcdef"


# ---- provider gate -----------------------------------------------------------------------------
@pytest.mark.parametrize("model,policy_", [
    ("acme/model-1", policy.TrainingPolicy.NO_TRAINING),
    ("SelfHost/llama", policy.TrainingPolicy.SELF_HOSTED),
    ("optout/model", policy.TrainingPolicy.OPT_OUT),
    ("trainer/model", policy.TrainingPolicy.MAY_TRAIN),
    ("groq/llama", policy.TrainingPolicy.MAY_TRAIN),
    ("typo/model", policy.TrainingPolicy.UNKNOWN),         # unrecognised policy word is not a permissive default
    ("stranger/model", policy.TrainingPolicy.UNKNOWN),
    ("acme", policy.TrainingPolicy.UNKNOWN),                # no provider part
    ("", policy.TrainingPolicy.UNKNOWN),
    (None, policy.TrainingPolicy.UNKNOWN),
    (42, policy.TrainingPolicy.UNKNOWN),
])
def test_classification(model, policy_):
    assert policy.classify(model, DECLARED, FREE) == policy_


def test_only_explicit_no_training_or_self_hosted_pass():
    assert policy.provider_gate(["acme/a"], DECLARED, FREE).allowed
    assert policy.provider_gate(["acme/a", "selfhost/b"], DECLARED, FREE).allowed
    for denied in (["optout/x"], ["trainer/x"], ["groq/x"], ["stranger/x"], ["typo/x"]):
        decision = policy.provider_gate(denied, DECLARED, FREE)
        assert (decision.allowed, decision.reason, decision.denied_models) == (False, "provider_not_cleared", tuple(denied))


def test_one_bad_fallback_denies_the_whole_chain_and_an_empty_chain_denies():
    assert policy.provider_gate(["acme/a", "stranger/b"], DECLARED, FREE).denied_models == ("stranger/b",)
    assert policy.provider_gate([], DECLARED, FREE).reason == "no_model"


def test_free_tier_listing_beats_an_allowing_declaration():
    assert not policy.provider_gate(["acme/a"], "acme=no_training", "acme").allowed


def test_conflicting_or_malformed_declarations_fail_closed():
    assert not policy.provider_gate(["acme/a"], "acme=no_training,acme=self_hosted", "").allowed   # same provider, two answers
    assert not policy.provider_gate(["acme/a"], "acme", "").allowed
    assert not policy.provider_gate(["acme/a"], "=no_training,,acme=", "").allowed


def test_defaults_come_from_settings_and_an_empty_config_allows_nothing(monkeypatch):
    monkeypatch.setattr(policy.settings, "llm_provider_training_policies", "")
    assert not policy.provider_gate(["acme/a"]).allowed
    monkeypatch.setattr(policy.settings, "llm_provider_training_policies", "acme=no_training")
    assert policy.provider_gate(["acme/a"]).allowed


def test_decisions_are_deterministic():
    assert {policy.provider_gate(["acme/a", "x/y"], DECLARED, FREE) for _ in range(20)} == {policy.provider_gate(["acme/a", "x/y"], DECLARED, FREE)}


@pytest.mark.parametrize("consented", [False, None, 1, "yes"])
def test_model_use_needs_literal_consent_before_the_provider_gate(consented):
    decision = policy.authorize_model_use(consented, ["acme/a"], DECLARED, FREE)
    assert (decision.allowed, decision.reason) == (False, "consent_required")


def test_model_use_requires_consent_and_a_cleared_provider():
    assert policy.authorize_model_use(True, ["acme/a"], DECLARED, FREE).allowed
    assert policy.authorize_model_use(True, ["groq/a"], DECLARED, FREE).reason == "provider_not_cleared"


# ---- minimization --------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["", "   ", "x" * 201, "has\x00nul", "line\nbreak", "zero​width", "mail me a@b.co",
                                 "call 0300 1234567", "card 4111 1111 1111 1111", "+92 (300) 123-4567"])
def test_text_that_is_empty_long_control_or_personal_is_rejected(bad):
    with pytest.raises(ValueError):
        policy.clean_text(bad)


def test_ordinary_preferences_pass_and_are_trimmed():
    assert policy.clean_text("  prefers plain, light colours  ") == "prefers plain, light colours"
    assert policy.clean_text("size 42, budget 5000") == "size 42, budget 5000"
    assert policy.clean_text("اونی شال") == "اونی شال"


# ---- strict request shapes ---------------------------------------------------------------------
def create(**over):
    return MemoryCreate(**{"idempotency_key": IDEM, "category": "preference", "key": "style", "value": "plain", "source": "user_explicit", **over})


def test_a_minimal_create_gets_the_default_retention():
    assert create().retention_days == policy.DEFAULT_RETENTION_DAYS


@pytest.mark.parametrize("over", [
    {"category": "weak_signal"}, {"category": "inferred"}, {"source": "model_inferred"}, {"source": "assistant"},
    {"key": "Has Caps"}, {"key": "1leading"}, {"key": ""}, {"key": "k" * 65},
    {"idempotency_key": "short"}, {"idempotency_key": "idem_" + "a" * 65}, {"idempotency_key": "nope_0123456789abcdef"},
    {"retention_days": 0}, {"retention_days": 366}, {"retention_days": "30"}, {"retention_days": 30.5}, {"retention_days": True},
    {"source_ref": "has space"}, {"source_ref": "x" * 65}, {"value": 7}, {"reason": "x" * 201}, {"customer_id": str(uuid.uuid4())},
    {"status": "deleted"}, {"expires_at": "2099-01-01T00:00:00Z"}, {"extra": 1},
])
def test_malformed_create_is_rejected(over):
    with pytest.raises(ValidationError):
        create(**over)


@pytest.mark.parametrize("payload", [{}, {"value": None}, {"reason": None}, {"key": "other"}, {"category": "preference"}, {"retention_days": 5},
                                     {"value": ""}, {"value": "a@b.co"}, {"value": 1}, {"customer_id": "x"}])
def test_malformed_update_is_rejected(payload):
    with pytest.raises(ValidationError):
        MemoryUpdate(**payload)


def test_update_accepts_value_and_or_reason_only():
    assert MemoryUpdate(value="new").reason is None and MemoryUpdate(reason="why").value is None


@pytest.mark.parametrize("granted", ["true", 1, 0, None, "yes"])
def test_consent_must_be_a_real_boolean(granted):
    with pytest.raises(ValidationError):
        ConsentRequest(granted=granted)


def test_every_refusal_has_a_status():
    assert {MemoryRejected(code).status for code in MemoryRejected.STATUS} == {403, 404, 409, 410}


# ---- route seam ----------------------------------------------------------------------------------
def test_without_customer_authentication_every_memory_route_is_refused():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pg_session] = lambda: None
    client = TestClient(app)
    item = uuid.uuid4()
    calls = [("get", "/v1/me/memory"), ("get", "/v1/me/memory/consent"), ("put", "/v1/me/memory/consent"), ("post", "/v1/me/memory"),
             ("get", f"/v1/me/memory/{item}"), ("patch", f"/v1/me/memory/{item}"), ("delete", f"/v1/me/memory/{item}"), ("delete", "/v1/me/memory")]
    for method, path in calls:
        assert getattr(client, method)(path, headers={"X-Admin-Key": "x", "X-Customer-Id": str(item)}).status_code in (401, 422), (method, path)
    assert client.get("/v1/me/memory").status_code == 401


def test_no_route_takes_a_customer_identifier_from_the_client():
    for route in router.routes:
        names = {p.name for p in route.dependant.path_params + route.dependant.query_params + route.dependant.header_params + route.dependant.cookie_params}
        assert not any("customer" in n or n == "user_id" for n in names), route.path
        assert memory_customer in {d.call for d in route.dependant.dependencies}, route.path
