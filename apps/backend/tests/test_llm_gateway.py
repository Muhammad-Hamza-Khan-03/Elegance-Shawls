import asyncio

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from configuration.config import settings
from llm.fake import FakeProvider, ProviderReply
from llm.gateway import (
    AllProvidersFailedError, BudgetExceededError, BudgetTracker, LLMError, LLMGateway, PersonalDataPolicyError,
)
from observability import tracing

MESSAGES = [{"role": "user", "content": "brown stole under four thousand"}]


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(settings, "llm_chain_default", "fake/a,fake/b,fake/c")
    monkeypatch.setattr(settings, "llm_production_chain", "fake/paid")
    monkeypatch.setattr(settings, "llm_free_tier_providers", "groq,gemini,openrouter")
    monkeypatch.setattr(settings, "llm_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_timeout_seconds", 0.2)


def gateway(fake=None, daily=1.0, total=10.0, completion=None) -> LLMGateway:
    return LLMGateway(completion=completion, fake=fake or FakeProvider(),
                      budget=BudgetTracker(daily, total, 0.8))


def run(coro):
    return asyncio.run(coro)


def test_first_model_answers_and_cost_is_recorded():
    gw = gateway(FakeProvider(reply="ok", cost_usd=0.002))
    result = run(gw.complete(MESSAGES))
    assert (result.text, result.model, result.attempts, result.fallback_used) == ("ok", "fake/a", 1, False)
    assert result.cost_usd == 0.002 and result.input_tokens > 0 and result.latency_ms >= 0
    assert gw.budget.spent_total == pytest.approx(0.002)


def test_falls_back_when_first_provider_is_disabled():
    fake = FakeProvider(failing={"fake/a"})
    result = run(gateway(fake).complete(MESSAGES))
    assert (result.model, result.attempts, result.fallback_used) == ("fake/b", 2, True)
    assert fake.calls == ["fake/a", "fake/b"]


def test_fallback_chain_is_bounded(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_attempts", 2)
    fake = FakeProvider(failing={"fake/a", "fake/b", "fake/c"})
    with pytest.raises(AllProvidersFailedError):
        run(gateway(fake).complete(MESSAGES))
    assert fake.calls == ["fake/a", "fake/b"]


def test_hanging_provider_times_out_and_falls_back():
    async def slow_then_fast(model, messages, timeout):
        if model == "slow/x":
            await asyncio.sleep(5)
        return ProviderReply("late")

    settings.llm_chain_default = "slow/x,other/y"
    result = run(gateway(completion=slow_then_fast).complete(MESSAGES))
    assert (result.model, result.fallback_used) == ("other/y", True)


def test_personal_data_never_reaches_free_tier_providers(monkeypatch):
    seen = []

    async def spy(model, messages, timeout):
        seen.append(model)
        return ProviderReply("x")

    monkeypatch.setattr(settings, "llm_production_chain", "groq/llama,gemini/flash,openrouter/free")
    with pytest.raises(PersonalDataPolicyError):
        run(gateway(completion=spy).complete(MESSAGES, personal=True))
    assert seen == []


def test_personal_data_uses_only_the_production_chain(monkeypatch):
    monkeypatch.setattr(settings, "llm_chain_default", "groq/llama,fake/a")
    monkeypatch.setattr(settings, "llm_production_chain", "groq/llama,fake/paid")
    fake = FakeProvider()
    result = run(gateway(fake).complete(MESSAGES, personal=True))
    assert result.model == "fake/paid" and fake.calls == ["fake/paid"]


def test_personal_data_with_no_production_chain_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "llm_production_chain", "")
    with pytest.raises(PersonalDataPolicyError):
        run(gateway().complete(MESSAGES, personal=True))


def test_unconfigured_default_chain_raises_llm_error(monkeypatch):
    monkeypatch.setattr(settings, "llm_chain_default", "")
    with pytest.raises(LLMError):
        run(gateway().complete(MESSAGES))


def test_daily_budget_warns_at_80_percent_then_blocks():
    gw = gateway(FakeProvider(cost_usd=0.001), daily=0.0025)
    first, second, third = (run(gw.complete(MESSAGES)) for _ in range(3))
    assert (first.budget_warning, second.budget_warning, third.budget_warning) == (False, True, True)
    with pytest.raises(BudgetExceededError):
        run(gw.complete(MESSAGES))


def test_environment_budget_blocks_even_when_daily_budget_remains():
    gw = gateway(FakeProvider(cost_usd=0.01), daily=100.0, total=0.015)
    run(gw.complete(MESSAGES))
    run(gw.complete(MESSAGES))
    with pytest.raises(BudgetExceededError):
        run(gw.complete(MESSAGES))


def test_spans_carry_llm_metadata_but_never_prompt_text():
    exporter = InMemorySpanExporter()
    tracing.add_exporter(exporter)
    run(gateway(FakeProvider(cost_usd=0.003)).complete(MESSAGES))
    spans = [s for s in exporter.get_finished_spans() if s.name == "llm.call"]
    assert spans
    attrs = dict(spans[-1].attributes)
    assert attrs["llm.model"] == "fake/a" and attrs["llm.cost_usd"] == 0.003 and attrs["llm.input_tokens"] > 0
    assert "brown stole" not in str(attrs)


def test_real_provider_without_litellm_degrades_instead_of_crashing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_litellm(name, *args, **kwargs):
        if name == "litellm":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_litellm)
    monkeypatch.setattr(settings, "llm_chain_default", "mistral/large")   # not a built-in provider -> LiteLLM
    with pytest.raises(AllProvidersFailedError):
        run(LLMGateway(budget=BudgetTracker(1, 1, 0.8)).complete(MESSAGES))


# --- shared budget ledger ---------------------------------------------------------------------
def test_budget_is_shared_between_two_instances_through_redis():
    from fakeredis import FakeAsyncRedis

    redis = FakeAsyncRedis()

    async def flow():
        a, b = BudgetTracker(0.0025, 10, 0.8, redis=redis), BudgetTracker(0.0025, 10, 0.8, redis=redis)
        await a.record(0.002)                    # instance A spends 80% of the daily budget
        warned = await b.record(0.0005)          # instance B sees A's spend and now reaches 100%
        with pytest.raises(BudgetExceededError):
            await b.check()
        with pytest.raises(BudgetExceededError):
            await a.check()                      # A is blocked by B's spend too
        return warned

    assert asyncio.run(flow()) is True


def test_budget_falls_back_to_the_local_ledger_when_redis_fails():
    class Broken:
        async def mget(self, *_):
            raise ConnectionError("down")

        async def incrbyfloat(self, *_):
            raise ConnectionError("down")

        async def expire(self, *_):
            raise ConnectionError("down")

    async def flow():
        tracker = BudgetTracker(0.001, 10, 0.8, redis=Broken())
        await tracker.record(0.002)
        with pytest.raises(BudgetExceededError):
            await tracker.check()

    asyncio.run(flow())


def test_shared_budget_is_per_environment(monkeypatch):
    from fakeredis import FakeAsyncRedis

    redis = FakeAsyncRedis()

    async def flow():
        monkeypatch.setattr(settings, "environment", "staging")
        await BudgetTracker(1, 10, 0.8, redis=redis).record(5)
        monkeypatch.setattr(settings, "environment", "development")
        await BudgetTracker(1, 10, 0.8, redis=redis).check()   # a different environment has its own ledger

    asyncio.run(flow())


# --- the real LiteLLM path, with the module stubbed (no network, no credentials) ---------------
def _stub_litellm(monkeypatch, *, cost=0.0042, cost_raises=False):
    import sys
    import types

    seen = {}

    async def acompletion(**kwargs):
        seen.update(kwargs)
        message = types.SimpleNamespace(content="real reply")
        usage = types.SimpleNamespace(prompt_tokens=11, completion_tokens=3)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)], usage=usage)

    def completion_cost(completion_response):
        if cost_raises:
            raise ValueError("unknown model price")
        return cost

    module = types.SimpleNamespace(acompletion=acompletion, completion_cost=completion_cost)
    monkeypatch.setitem(sys.modules, "litellm", module)
    return seen


def test_real_provider_path_maps_litellm_response_tokens_and_cost(monkeypatch):
    seen = _stub_litellm(monkeypatch)
    monkeypatch.setattr(settings, "llm_chain_default", "mistral/large")
    result = run(LLMGateway(budget=BudgetTracker(1, 10, 0.8)).complete(MESSAGES))
    assert (result.text, result.model, result.input_tokens, result.output_tokens, result.cost_usd) == (
        "real reply", "mistral/large", 11, 3, 0.0042)
    assert seen["model"] == "mistral/large" and seen["num_retries"] == 0 and seen["timeout"] == 0.2
    assert "api_key" not in seen                       # keys come from provider env vars, never from code


def test_unknown_price_is_recorded_as_zero_cost(monkeypatch):
    _stub_litellm(monkeypatch, cost_raises=True)
    monkeypatch.setattr(settings, "llm_chain_default", "mistral/large")
    assert run(LLMGateway(budget=BudgetTracker(1, 10, 0.8)).complete(MESSAGES)).cost_usd == 0.0
