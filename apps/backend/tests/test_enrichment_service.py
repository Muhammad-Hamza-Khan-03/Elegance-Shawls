"""Enrichment service with a fake provider: retries, timeouts, failure classes, budget and redacted logs. Zero network."""
import asyncio
import json
import logging
import socket

import httpx
import pytest

from configuration.config import settings
from enrichment.contract import FIELDS, FREE_TEXT, MAX_ATTEMPTS, allowed_values
from enrichment.service import build_input, generate, is_transient, prepare
from llm.fake import ProviderReply
from llm.gateway import BudgetTracker
from llm.openai_compatible import ProviderError

PRODUCT = {"name": "SECRET-NAME Ivory Stole", "main_description": "SECRET-DESC light stole, floral border.",
           "category": "stoles", "price": 4000, "variants": [{"name": "x", "color": "Cream", "stock": 3}, {"name": "y", "color": None}]}
PAYLOAD, _ = prepare(PRODUCT)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("network access in a fake-provider test")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(settings, "enrichment_backoff_seconds", 1.0)
    monkeypatch.setattr(settings, "enrichment_backoff_cap_seconds", 8.0)


def good_reply() -> str:
    data = {f: {"value": sorted(allowed_values(f))[0], "reason": None} for f in FIELDS if f not in FREE_TEXT}
    data.update({f: {"value": "A light stole.", "reason": None} for f in FREE_TEXT})
    return json.dumps(data)


class Script:
    """Provider double: each call pops the next outcome (an exception to raise, or reply text)."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    async def __call__(self, model, messages, timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return await outcome()
        return ProviderReply(outcome, input_tokens=10, output_tokens=5, cost_usd=0.001)


class Sleeps(list):
    async def __call__(self, seconds):
        self.append(seconds)


def run(script, **kw):
    budget = kw.pop("budget", None) or BudgetTracker(1.0, 10.0, 0.8)
    sleeps = Sleeps()
    result = asyncio.run(generate(script, "fake/model", PAYLOAD, budget=budget, sleep=sleeps, **kw))
    return result, sleeps


def test_input_contains_only_name_category_description_and_colours():
    assert set(build_input(PRODUCT)) == {"name", "category", "description", "colors"}
    assert build_input(PRODUCT)["colors"] == ["Cream"]
    assert "4000" not in json.dumps(build_input(PRODUCT))


def test_success_on_first_attempt():
    result, sleeps = run(Script(good_reply()))
    assert (result.status, result.attempts, sleeps) == ("succeeded", 1, [])
    assert set(result.suggestions) == set(FIELDS)


@pytest.mark.parametrize("transient", [
    ConnectionError("down"), httpx.ConnectError("x"), httpx.ReadTimeout("x"),
    ProviderError("groq returned HTTP 429"), ProviderError("groq returned HTTP 503"), ProviderError("gemini returned HTTP 500"),
])
def test_transient_errors_retry_once_with_backoff_then_succeed(transient):
    script = Script(transient, good_reply())
    result, sleeps = run(script)
    assert (result.status, result.attempts, script.calls, sleeps) == ("succeeded", 2, 2, [1.0])


def test_transient_errors_stop_after_the_attempt_cap():
    script = Script(ConnectionError("a"), ConnectionError("b"), good_reply())
    result, _ = run(script)
    assert (result.status, result.attempts, script.calls) == ("failed", MAX_ATTEMPTS, 2)
    assert result.last_error == "ConnectionError"


@pytest.mark.parametrize("permanent", [
    ProviderError("groq returned HTTP 401"), ProviderError("groq returned HTTP 403"), ProviderError("groq returned HTTP 400"),
    ProviderError("GROQ_API_KEY is not set"), ValueError("bad"), KeyError("choices"),
])
def test_permanent_errors_never_retry(permanent):
    script = Script(permanent, good_reply())
    result, sleeps = run(script)
    assert (result.status, result.attempts, script.calls, sleeps) == ("failed", 1, 1, [])


def test_timeout_retries_within_the_bound(monkeypatch):
    monkeypatch.setattr(settings, "llm_timeout_seconds", 0.05)

    async def hang():
        await asyncio.sleep(5)

    script = Script(hang, hang, good_reply())
    result, sleeps = run(script)
    assert (result.status, script.calls, result.last_error) == ("failed", 2, "TimeoutError") and sleeps == [1.0]


def test_backoff_is_capped(monkeypatch):
    from enrichment import service
    monkeypatch.setattr(settings, "enrichment_backoff_seconds", 100.0)
    assert service._backoff(1) == 8.0


@pytest.mark.parametrize("reply", ["not json", "[]", json.dumps({"fabric": {"value": "silk", "reason": None}})])
def test_schema_failures_are_permanent_and_recorded(reply):
    script = Script(reply, good_reply())
    result, _ = run(script)
    assert (result.status, result.attempts, script.calls, result.last_error) == ("failed", 1, 1, "schema_invalid")
    assert result.suggestions is None and result.validation_errors


def test_vocabulary_violation_is_rejected():
    data = json.loads(good_reply())
    data["pattern"] = {"value": "tartan", "reason": None}
    result, _ = run(Script(json.dumps(data)))
    assert result.status == "failed" and any("vocabulary" in e for e in result.validation_errors)


def test_spent_budget_blocks_the_call():
    spent = BudgetTracker(0.0, 10.0, 0.8)
    script = Script(good_reply())
    result, _ = run(script, budget=spent)
    assert (result.status, script.calls, result.last_error) == ("failed", 0, "budget_exceeded")


def test_a_successful_call_is_charged_to_the_budget():
    budget = BudgetTracker(1.0, 10.0, 0.8)
    run(Script(good_reply()), budget=budget)
    assert budget.spent_total == pytest.approx(0.001)


def test_on_retry_false_stops_and_reports_cancelled():
    async def stop(error):
        return False

    script = Script(ConnectionError("a"), good_reply())
    result, _ = run(script, on_retry=stop)
    assert (result.status, script.calls) == ("cancelled", 1)


@pytest.mark.parametrize("exc,expected", [
    (TimeoutError(), True), (ConnectionResetError(), True), (httpx.ConnectTimeout("x"), True),
    (ProviderError("openrouter returned HTTP 502"), True), (ProviderError("groq returned HTTP 404"), False),
    (ProviderError("groq returned HTTP 422"), False), (RuntimeError("x"), False),
])
def test_transient_classification(exc, expected):
    assert is_transient(exc) is expected


def test_logs_are_redacted(caplog):
    caplog.set_level(logging.DEBUG)
    leaked = json.loads(good_reply())
    leaked["description"] = {"value": "SECRET-OUTPUT text", "reason": None}
    run(Script(ConnectionError("SECRET-PROMPT in error"), json.dumps(leaked)))
    run(Script("SECRET-RAW-RESPONSE"))
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "enrichment_reply" in text and "enrichment_provider_error" in text
    for secret in ("SECRET-NAME", "SECRET-DESC", "SECRET-OUTPUT", "SECRET-PROMPT", "SECRET-RAW-RESPONSE", "Cream", "4000"):
        assert secret not in text
