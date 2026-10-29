"""LiteLLM gateway: logical names -> provider chains, bounded fallback, budgets, privacy policy.

Policy lives here in code, not in prompts:
* a call flagged personal=True is never routed to a free-tier (may-train) provider;
* the fallback chain is bounded by LLM_MAX_ATTEMPTS and a per-call timeout;
* daily and per-environment budgets block calls once spent; a warning fires at 80%.
Callers must degrade to normal browsing/search when LLMError is raised.
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Awaitable, Callable

from configuration.config import settings
from database.redis_client import get_redis
from llm.fake import FakeProvider, ProviderReply
from llm.openai_compatible import openai_compatible_completion, supports
from observability.langfuse_client import record_generation
from observability.tracing import current_ids, set_attrs, span

logger = logging.getLogger("elegance.llm")

Completion = Callable[[str, list[dict], float], Awaitable[ProviderReply]]


class LLMError(RuntimeError):
    pass


class PersonalDataPolicyError(LLMError):
    """personal=True but no eligible (no-training / self-hosted) provider is configured."""


class BudgetExceededError(LLMError):
    pass


class AllProvidersFailedError(LLMError):
    pass


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    attempts: int
    fallback_used: bool
    budget_warning: bool


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def provider_of(model: str) -> str:
    return model.split("/", 1)[0].lower()


def is_free_tier(model: str) -> bool:
    return provider_of(model) in {p.lower() for p in _csv(settings.llm_free_tier_providers)}


class BudgetTracker:
    """Daily and per-environment spend ledger, shared through Redis when it is configured.

    Every instance also keeps a local ledger and checks max(local, shared), so a Redis outage
    degrades to per-instance accounting instead of disabling the budget. shortcut: the shared
    counters are not atomic with the provider call, so concurrent calls can overshoot by one
    call's cost; move to a reservation scheme before real paid traffic.
    """

    def __init__(self, daily_limit: float, environment_limit: float, warn_ratio: float, redis=None):
        self.daily_limit, self.environment_limit, self.warn_ratio = daily_limit, environment_limit, warn_ratio
        self._redis = redis
        self.spent_total = 0.0
        self._daily: dict[str, float] = {}

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    @property
    def spent_today(self) -> float:
        return self._daily.get(self._today(), 0.0)

    def _client(self):
        return self._redis if self._redis is not None else get_redis()

    def _keys(self) -> tuple[str, str]:
        return f"llm:spend:{settings.environment}:{self._today()}", f"llm:spend:{settings.environment}:total"

    async def _spent(self) -> tuple[float, float]:
        """(today, total), taking the larger of the local and shared ledgers."""
        today, total = self.spent_today, self.spent_total
        client = self._client()
        if client is not None:
            try:
                day_key, total_key = self._keys()
                shared_day, shared_total = await client.mget(day_key, total_key)
                today = max(today, float(shared_day or 0))
                total = max(total, float(shared_total or 0))
            except Exception:
                logger.warning("Redis budget ledger unavailable; using the local ledger")
        return today, total

    async def check(self) -> None:
        today, total = await self._spent()
        if today >= self.daily_limit:
            raise BudgetExceededError("Daily LLM budget is spent")
        if total >= self.environment_limit:
            raise BudgetExceededError("Environment LLM budget is spent")

    async def record(self, cost: float) -> bool:
        """Adds a cost and returns True when either budget is at or above the warning ratio."""
        day = self._today()
        self._daily = {day: self._daily.get(day, 0.0) + cost}
        self.spent_total += cost
        client = self._client()
        if client is not None:
            try:
                day_key, total_key = self._keys()
                await client.incrbyfloat(day_key, cost)
                await client.expire(day_key, 3 * 24 * 3600)
                await client.incrbyfloat(total_key, cost)
            except Exception:
                logger.warning("Redis budget ledger unavailable; cost recorded locally only")
        today, total = await self._spent()
        warn = (today >= self.warn_ratio * self.daily_limit
                or total >= self.warn_ratio * self.environment_limit)
        if warn:
            logger.warning("LLM budget above %d%%: today=%.4f/%.2f total=%.4f/%.2f", int(self.warn_ratio * 100),
                           today, self.daily_limit, total, self.environment_limit)
        return warn


async def _litellm_completion(model: str, messages: list[dict], timeout: float) -> ProviderReply:
    try:
        import litellm  # imported lazily: slow and unnecessary for tests and the catalogue
    except ImportError as exc:  # optional dependency, see requirements-llm.txt
        raise LLMError("litellm is not installed (requirements-llm.txt)") from exc

    response = await litellm.acompletion(model=model, messages=messages, timeout=timeout, num_retries=0)
    try:
        cost = float(litellm.completion_cost(completion_response=response) or 0.0)
    except Exception:  # unknown price (e.g. a free or local model) is recorded as zero
        cost = 0.0
    usage = getattr(response, "usage", None)
    return ProviderReply(
        text=response.choices[0].message.content or "",
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cost_usd=cost,
    )


async def _route_completion(model: str, messages: list[dict], timeout: float) -> ProviderReply:
    """Built-in client for Groq/Gemini/OpenRouter/Ollama; LiteLLM (optional) for any other provider."""
    if supports(model):
        return await openai_compatible_completion(model, messages, timeout)
    return await _litellm_completion(model, messages, timeout)


class LLMGateway:
    def __init__(self, completion: Completion | None = None, fake: FakeProvider | None = None,
                 budget: BudgetTracker | None = None):
        self._completion = completion or _route_completion
        self._fake = fake or FakeProvider()
        self.budget = budget or BudgetTracker(
            settings.llm_daily_budget_usd, settings.llm_environment_budget_usd, settings.llm_budget_warn_ratio)

    def chain(self, logical: str = "default", personal: bool = False) -> list[str]:
        """Logical name -> ordered models. personal=True forces the production chain, minus free tiers."""
        configured = settings.llm_production_chain if personal else (
            settings.llm_production_chain if logical == "production" else settings.llm_chain_default)
        models = _csv(configured)
        if personal:
            models = [m for m in models if not is_free_tier(m)]
            if not models:
                raise PersonalDataPolicyError("No no-training provider is configured for personal data")
        if not models:
            raise LLMError(f"No models are configured for '{logical}'")
        return models[: max(1, settings.llm_max_attempts)]

    async def complete(self, messages: list[dict], logical: str = "default", personal: bool = False) -> LLMResult:
        models = self.chain(logical, personal)
        await self.budget.check()
        last_error: Exception | None = None
        for attempt, model in enumerate(models, start=1):
            started = perf_counter()
            call = self._fake if model.startswith("fake/") else self._completion
            try:
                with span("llm.call", **{"llm.model": model, "llm.logical": logical,
                                         "llm.personal": personal, "llm.attempt": attempt}) as current:
                    reply = await asyncio.wait_for(call(model, messages, settings.llm_timeout_seconds),
                                                   settings.llm_timeout_seconds)
                    latency = round((perf_counter() - started) * 1000, 1)
                    set_attrs(current, **{"llm.input_tokens": reply.input_tokens, "llm.output_tokens": reply.output_tokens,
                                          "llm.cost_usd": reply.cost_usd, "llm.latency_ms": latency})
                    trace_id, span_id = current_ids()
                    record_generation(model=model, logical=logical, input_tokens=reply.input_tokens,
                                      output_tokens=reply.output_tokens, cost_usd=reply.cost_usd,
                                      latency_ms=latency, trace_id=trace_id, parent_span_id=span_id)
            except Exception as exc:  # any provider failure moves to the next model
                last_error = exc
                logger.warning(json.dumps({"event": "llm_fallback", "model": model, "error": type(exc).__name__}))
                continue
            warning = await self.budget.record(reply.cost_usd)
            result = LLMResult(reply.text, model, reply.input_tokens, reply.output_tokens, reply.cost_usd,
                               latency, attempt, attempt > 1, warning)
            logger.info(json.dumps({"event": "llm_call", "model": model, "attempts": attempt,
                                    "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
                                    "cost_usd": reply.cost_usd, "latency_ms": latency}))
            return result
        raise AllProvidersFailedError(f"All {len(models)} providers failed") from last_error


_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
