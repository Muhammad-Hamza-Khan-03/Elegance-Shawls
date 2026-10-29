"""Enrichment orchestration: bounded provider calls with strict validation, persisted as a reviewable suggestion.

Only repositories.enrichment is written here. Catalogue products, variants, attributes and staged-product state are
never touched, and logs carry ids, model and error classes only (never prompts, product text or model output).
"""
import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from configuration.config import settings
from enrichment.contract import MAX_ATTEMPTS, input_hash, parse_response, sanitize
from enrichment.prompts import build_messages
from llm.fake import ProviderReply
from llm.gateway import BudgetExceededError, BudgetTracker, _route_completion, get_gateway
from llm.openai_compatible import ProviderError
from repositories import enrichment as repo
from repositories import staged as staged_repo

logger = logging.getLogger("elegance.enrichment")
Complete = Callable[[str, list[dict], float], Awaitable[ProviderReply]]
NOT_REVIEWABLE = ("rejected", "archived")
_HTTP_STATUS = re.compile(r"HTTP (\d{3})")


def build_input(product: dict) -> dict:
    """The only data a provider sees: name, category, description and variant colours of the staged draft. No price/stock/images."""
    colors = sorted({str(v["color"]).strip() for v in product.get("variants") or [] if isinstance(v, dict) and v.get("color")})
    return {"name": sanitize(str(product.get("name") or ""), 200), "category": product.get("category"),
            "description": sanitize(str(product.get("main_description") or ""), 1500), "colors": colors[:10]}


def prepare(product: dict) -> tuple[dict, str]:
    payload = build_input(product)
    return payload, input_hash(payload)


def is_transient(exc: BaseException) -> bool:
    """Timeouts, connection failures, HTTP 429 and 5xx retry; auth, policy, other 4xx and schema errors never do."""
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError)):
        return True
    if isinstance(exc, ProviderError) and (found := _HTTP_STATUS.search(str(exc))):
        return int(found.group(1)) == 429 or int(found.group(1)) >= 500
    return False


def describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}" if isinstance(exc, ProviderError) else type(exc).__name__  # ProviderError text is status-only


@dataclass
class Result:
    status: str                      # succeeded | failed | cancelled
    suggestions: dict | None = None
    validation_errors: list[str] = field(default_factory=list)
    last_error: str | None = None
    attempts: int = 0


def _backoff(retry: int) -> float:
    return min(settings.enrichment_backoff_cap_seconds, settings.enrichment_backoff_seconds * 2 ** (retry - 1))


async def generate(complete: Complete, model: str, payload: dict, *, budget: BudgetTracker,
                   on_retry: Callable[[str], Awaitable[bool]] | None = None, sleep=asyncio.sleep,
                   log_id: str = "-") -> Result:
    """At most MAX_ATTEMPTS provider calls; only transient errors retry (capped exponential backoff)."""
    messages = build_messages(payload)
    source_text = f"{payload['name']} {payload['description']}"
    timeout = settings.llm_timeout_seconds
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            if on_retry is not None and not await on_retry(last_error):
                return Result("cancelled", last_error=last_error, attempts=attempt - 1)
            await sleep(_backoff(attempt - 1))
        try:
            await budget.check()
            reply = await asyncio.wait_for(complete(model, messages, timeout), timeout)
        except Exception as exc:
            last_error = "budget_exceeded" if isinstance(exc, BudgetExceededError) else describe(exc)
            retry = attempt < MAX_ATTEMPTS and is_transient(exc)
            logger.warning(json.dumps({"event": "enrichment_provider_error", "id": log_id, "model": model,
                                       "attempt": attempt, "error": last_error, "retry": retry}))
            if retry:
                continue
            return Result("failed", last_error=last_error, attempts=attempt)
        await budget.record(reply.cost_usd)
        parsed = parse_response(reply.text, source_text)
        logger.info(json.dumps({"event": "enrichment_reply", "id": log_id, "model": model, "attempt": attempt,
                                "valid": not parsed.errors, "error_count": len(parsed.errors),
                                "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
                                "cost_usd": reply.cost_usd}))
        if parsed.errors:
            return Result("failed", validation_errors=parsed.errors, last_error="schema_invalid", attempts=attempt)
        return Result("succeeded", suggestions=parsed.suggestions, attempts=attempt)
    raise AssertionError("unreachable")  # every loop iteration returns or continues


async def process(sessions: async_sessionmaker, suggestion_id, *, complete: Complete | None = None,
                  budget: BudgetTracker | None = None, sleep=asyncio.sleep) -> str:
    """Run one queued suggestion to a final state. Database transactions are short; none spans a provider call."""
    async with sessions() as session, session.begin():
        row = await repo.claim(session, suggestion_id)
        staged = await staged_repo.get_staged(session, row.staged_product_id) if row else None
    if row is None:
        return "skipped"  # cancelled, finished or claimed by another delivery of the same job

    async def finish(**values) -> str:
        async with sessions() as session, session.begin():
            done = await repo.finish(session, suggestion_id, **values)
        return done.status if done else "cancelled"  # lost the race to an explicit cancel

    if staged is None or staged.status in NOT_REVIEWABLE:
        return await finish(status="cancelled", last_error="staged_product_not_reviewable")
    payload, current_hash = prepare(staged.product)
    if current_hash != row.input_content_hash:
        return await finish(status="failed", last_error="input_changed")  # the draft moved on since it was queued

    async def on_retry(error: str) -> bool:
        async with sessions() as session, session.begin():
            return await repo.begin_retry(session, suggestion_id, error)

    result = await generate(complete or _route_completion, row.model, payload, budget=budget or get_gateway().budget,
                            on_retry=on_retry, sleep=sleep, log_id=str(suggestion_id))
    if result.status == "cancelled":
        return await finish(status="cancelled", last_error=result.last_error)
    final = await finish(status=result.status, suggestions=result.suggestions,
                         validation_errors=result.validation_errors, last_error=result.last_error)
    logger.info(json.dumps({"event": "enrichment_finished", "id": str(suggestion_id), "status": final,
                            "attempts": result.attempts, "trace_id": row.trace_id}))
    return final
