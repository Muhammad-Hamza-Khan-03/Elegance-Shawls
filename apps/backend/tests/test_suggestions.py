from datetime import datetime, timedelta, timezone
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suggestions.engine import MemoryFact, ProductFact, VariantFact, build_suggestions
from routes.suggestion_routes import router

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
PRODUCT = uuid.UUID("10000000-0000-0000-0000-000000000001")
VARIANT = uuid.UUID("20000000-0000-0000-0000-000000000001")
MEMORY = uuid.UUID("30000000-0000-0000-0000-000000000001")


def memory(**overrides):
    values = dict(id=MEMORY, customer_id=USER, category="preference", key="colour", value="blue",
                  source="user_explicit", source_ref="memory-page-7", version=1, status="active",
                  expires_at=NOW + timedelta(days=1), updated_at=NOW)
    return MemoryFact(**(values | overrides))


def product(**overrides):
    values = dict(id=PRODUCT, slug="blue-shawl", name="Blue Shawl", category="shawls", status="active",
                  is_active=True, revision=4, catalogue_fresh_at=NOW,
                  variants=(VariantFact(VARIANT, "Standard", "Blue", "Free Size", 2, True),))
    return ProductFact(**(values | overrides))


def build(memories=(memory(),), products=(product(),), **overrides):
    values = dict(principal_customer_id=USER, consented=True, memories=memories, products=products,
                  generated_at=NOW, provider_models=("selfhost/llama",),
                  declared_provider_policies="selfhost=self_hosted", free_tier_providers="")
    return build_suggestions(**(values | overrides))


def test_reason_contains_stable_code_text_memory_provenance_product_evidence_policy_timestamp_and_version():
    [candidate] = build()
    assert candidate.reason.code == "explicit_colour_match"
    assert candidate.reason.text == "Matches your explicit colour preference."
    assert candidate.reason.source_memory_ids == (MEMORY,)
    assert candidate.reason.source_provenance == ("memory-page-7",)
    assert candidate.reason.product_evidence.product_id == PRODUCT
    assert candidate.reason.product_evidence.product_revision == 4
    assert candidate.reason.product_evidence.variant_id == VARIANT
    assert candidate.reason.policy.decision == "allowed"
    assert candidate.reason.generated_at == NOW
    assert candidate.engine_version == "m4-s4.1"


def test_reproducibility_is_byte_for_byte_for_same_inputs():
    assert build() == build()


@pytest.mark.parametrize("bad", [
    memory(status="deleted"), memory(expires_at=NOW), memory(version=0),
    memory(category="purchase_context"), memory(source="assistant"), memory(value="not blue"),
])
def test_empty_deleted_stale_ambiguous_or_unapproved_memory_yields_no_suggestion(bad):
    assert build(memories=(bad,)) == ()


def test_correction_invalidates_old_fact_and_only_new_explicit_fact_can_match():
    old = memory(value="red")
    corrected = memory(id=uuid.UUID("30000000-0000-0000-0000-000000000002"), value="blue")
    assert build(memories=(old,)) == ()
    assert len(build(memories=(corrected,))) == 1


def test_duplicate_active_memory_key_is_ambiguous_even_when_values_agree():
    duplicate = memory(id=uuid.UUID("30000000-0000-0000-0000-000000000002"), value="blue")
    assert build(memories=(memory(), duplicate)) == ()
    assert build(memories=(memory(), duplicate)) == build(memories=(memory(), duplicate))


def test_conflicting_active_memory_key_is_ambiguous():
    conflicting = memory(id=uuid.UUID("30000000-0000-0000-0000-000000000002"), value="red")
    assert build(memories=(memory(), conflicting)) == ()


def test_catalogue_freshness_is_required_and_boundary_is_inclusive():
    from suggestions.engine import CATALOGUE_FRESHNESS_MAX_AGE

    assert build(products=(product(catalogue_fresh_at=None),)) == ()
    assert build(products=(product(catalogue_fresh_at=NOW - CATALOGUE_FRESHNESS_MAX_AGE - timedelta(microseconds=1)),)) == ()
    assert len(build(products=(product(catalogue_fresh_at=NOW - CATALOGUE_FRESHNESS_MAX_AGE),))) == 1
    assert build(products=(product(catalogue_fresh_at=NOW + timedelta(microseconds=1)),)) == ()


def test_cross_user_memory_is_never_used():
    assert build(memories=(memory(customer_id=OTHER),)) == ()


def test_sensitive_fabric_identity_and_unlisted_free_text_are_not_inferred_or_leaked():
    facts = (
        memory(key="material", value="silk"),
        memory(id=uuid.uuid4(), key="email", value="blue@example.com"),
        memory(id=uuid.uuid4(), key="notes", value="blue looks good"),
    )
    assert build(memories=facts) == ()


def test_provider_and_consent_policy_fail_closed():
    assert build(consented=False) == ()
    assert build(provider_models=("trainer/model",), declared_provider_policies="trainer=may_train") == ()
    assert build(provider_models=("unknown/model",), declared_provider_policies="") == ()
    assert build(provider_models=()) == ()


def test_current_catalogue_only_and_out_of_stock_variants_are_not_suggested():
    assert build(products=(product(status="archived"),)) == ()
    assert build(products=(product(variants=(VariantFact(VARIANT, "Standard", "Blue", "Free Size", 0, True),),),)) == ()
    assert build(products=(product(revision=0),)) == ()


def test_allowed_explicit_fields_are_exact_and_typed():
    assert build(memories=(memory(key="size", value="free size"),), products=(product(),))[0].reason.code == "explicit_size_match"
    assert build(memories=(memory(key="category", value="SHAWLS"),))[0].reason.code == "explicit_category_match"
    assert build(memories=(memory(key="style", value="blue-shawl"),))[0].reason.code == "explicit_style_match"


def test_engine_has_no_model_or_network_imports():
    source = Path(__file__).parents[1].joinpath("suggestions", "engine.py").read_text()
    for forbidden in ("httpx", "requests", "urllib", "socket", "openai", "litellm", "provider_completion"):
        assert forbidden not in source


def test_route_requires_server_principal():
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/v1/me/suggestions").status_code == 401
