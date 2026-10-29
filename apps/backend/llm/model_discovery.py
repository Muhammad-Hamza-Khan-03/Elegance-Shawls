"""Safe, advisory Groq/Gemini model discovery with bounded caching.

Provider credentials are deliberately read from os.environ only inside the request
method. This module stores normalized metadata only; raw provider responses and
credentials never enter cache values, exceptions, or logs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from configuration.config import settings
from database.redis_client import get_redis

logger = logging.getLogger("elegance.llm.discovery")

PROVIDERS = ("groq", "gemini")
CACHE_KEYS = {p: f"llm:models:{p}" for p in PROVIDERS}
CATALOG_KEY = "llm:models:catalog"
_MAX_BODY = 1_000_000
_MAX_PAGES = 10

_memory: dict[str, str] = {}
_locks = {p: asyncio.Lock() for p in PROVIDERS}
_inflight: dict[str, asyncio.Task[str]] = {}
_background: dict[str, asyncio.Task] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _safe_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value and len(value) <= 500 else None


def _status(value: Any) -> str:
    return "available" if value is True or value in ("active", "AVAILABLE") else "deprecated" if value in (False, "deprecated", "DEPRECATED") else "available"


def _groq_models(payload: Any, refreshed_at: str) -> list[dict[str, Any]]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("malformed")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        model_id = row["id"]
        result.append({
            "provider": "groq", "model_id": f"groq/{model_id}",
            "display_name": model_id, "status": _status(row.get("active")),
            "generation_methods": ["chat"],
            "context_window": _safe_int(row.get("context_window")),
            "max_output_tokens": _safe_int(row.get("max_completion_tokens")),
            "version": None, "deprecation_notice": None, "deprecation_date": None,
            "refreshed_at": refreshed_at,
        })
    return result


def _gemini_models(payload: Any, refreshed_at: str) -> tuple[list[dict[str, Any]], str | None]:
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("malformed")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        methods = row.get("supportedGenerationMethods")
        if not isinstance(methods, list) or "generateContent" not in methods:
            continue
        name = row["name"]
        model_name = name.removeprefix("models/")
        if not model_name or len(model_name) > 300:
            continue
        result.append({
            "provider": "gemini", "model_id": f"gemini/{model_name}",
            "display_name": _safe_str(row.get("displayName")), "status": "available",
            "generation_methods": [m for m in methods if isinstance(m, str) and len(m) <= 100][:20],
            "context_window": _safe_int(row.get("inputTokenLimit")),
            "max_output_tokens": _safe_int(row.get("outputTokenLimit")),
            "version": _safe_str(row.get("version")),
            "deprecation_notice": None, "deprecation_date": None,
            "refreshed_at": refreshed_at,
        })
    token = payload.get("nextPageToken")
    return result, token if isinstance(token, str) and len(token) <= 500 else None


def _envelope(models: list[dict[str, Any]], refreshed_at: str, *, last_ok_at: str | None,
              state: str, error_kind: str | None) -> dict[str, Any]:
    return {"models": models, "refreshed_at": refreshed_at, "last_ok_at": last_ok_at,
            "state": state, "error_kind": error_kind}


class ModelDiscovery:
    def __init__(self, client_factory: Callable[..., Any] | None = None):
        self.client_factory = client_factory or (lambda **kwargs: httpx.AsyncClient(**kwargs))

    async def _request_json(self, provider: str, url: str, *, headers: dict[str, str], params: dict[str, str] | None = None) -> Any:
        # Environment lookup is intentionally here, at call time, and never persisted.
        key_name = "GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"
        key = os.environ.get(key_name)
        if not key:
            raise RuntimeError("not_configured")
        safe_headers = {"Authorization": f"Bearer {key}"} if provider == "groq" else {"x-goog-api-key": key}
        attempts = max(1, min(settings.llm_discovery_max_attempts, 4))
        for attempt in range(attempts):
            try:
                async with self.client_factory(timeout=settings.llm_discovery_timeout_seconds, follow_redirects=False) as client:
                    response = await client.get(url, headers={**headers, **safe_headers}, params=params)
                if response.status_code in (401, 403):
                    raise RuntimeError("unauthorized")
                retryable = response.status_code == 429 or 500 <= response.status_code < 600
                if retryable and attempt + 1 < attempts:
                    retry_after = response.headers.get("retry-after", "")
                    try:
                        delay = min(float(retry_after), settings.llm_discovery_retry_after_cap_seconds)
                    except (TypeError, ValueError):
                        delay = 0.0
                    await asyncio.sleep(max(0.0, delay))
                    continue
                if response.status_code >= 400:
                    raise RuntimeError("provider_error")
                body = response.content
                if len(body) > _MAX_BODY:
                    raise RuntimeError("oversized")
                return json.loads(body)
            except httpx.TimeoutException:
                if attempt + 1 >= attempts:
                    raise RuntimeError("timeout")
            except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
                raise RuntimeError("malformed")
        raise RuntimeError("provider_error")

    async def fetch(self, provider: str) -> list[dict[str, Any]]:
        refreshed = _now()
        if provider == "groq":
            payload = await self._request_json(provider, "https://api.groq.com/openai/v1/models", headers={})
            return _groq_models(payload, refreshed)
        if provider != "gemini":
            raise ValueError("provider")
        all_models: list[dict[str, Any]] = []
        token = None
        for _ in range(_MAX_PAGES):
            params = {"pageSize": "100"}
            if token:
                params["pageToken"] = token
            payload = await self._request_json(provider, "https://generativelanguage.googleapis.com/v1beta/models", headers={}, params=params)
            models, token = _gemini_models(payload, refreshed)
            all_models.extend(models)
            if not token:
                break
        return all_models

    async def refresh(self, provider: str) -> str:
        if provider not in PROVIDERS:
            raise ValueError("provider")
        task = _inflight.get(provider)
        if task is None or task.done():
            task = asyncio.create_task(self._refresh(provider))
            _inflight[provider] = task

            def clear_inflight(completed: asyncio.Task[str]) -> None:
                if _inflight.get(provider) is completed:
                    _inflight.pop(provider, None)

            task.add_done_callback(clear_inflight)
        return await asyncio.shield(task)

    async def _refresh(self, provider: str) -> str:
        async with _locks[provider]:
            redis = get_redis()
            lock_key = f"{CACHE_KEYS[provider]}:lock"
            token = secrets.token_hex(16)
            acquired = True
            try:
                if redis is not None:
                    acquired = bool(await redis.set(lock_key, token, nx=True, px=30_000))
                if not acquired:
                    current = await self.read(provider)
                    return current["state"] if current else "busy"
                try:
                    models = await self.fetch(provider)
                    envelope = _envelope(models, _now(), last_ok_at=_now(), state="ok", error_kind=None)
                except Exception as exc:
                    current = await self._load(provider)
                    kind = str(exc) if str(exc) in {"not_configured", "unauthorized", "timeout", "provider_error", "malformed", "oversized"} else "provider_error"
                    envelope = _envelope(current.get("models", []) if current else [], current.get("refreshed_at", _now()) if current else _now(), last_ok_at=current.get("last_ok_at") if current else None, state="not_configured" if kind == "not_configured" else "error", error_kind=kind)
                await self._save(provider, envelope)
                return envelope["state"]
            finally:
                if redis is not None and acquired:
                    try:
                        await redis.delete(lock_key)
                    except Exception:
                        pass

    async def _load(self, provider: str) -> dict[str, Any] | None:
        raw = None
        redis = get_redis()
        try:
            raw = await redis.get(CACHE_KEYS[provider]) if redis is not None else _memory.get(CACHE_KEYS[provider])
            if isinstance(raw, bytes): raw = raw.decode()
            return json.loads(raw) if raw else None
        except (Exception, json.JSONDecodeError):
            return None

    async def _save(self, provider: str, envelope: dict[str, Any]) -> None:
        raw = json.dumps(envelope, separators=(",", ":"))
        redis = get_redis()
        try:
            if redis is not None:
                await redis.set(CACHE_KEYS[provider], raw, px=int(settings.llm_discovery_stale_ceiling_seconds * 1000))
            else:
                _memory[CACHE_KEYS[provider]] = raw
        except Exception:
            _memory[CACHE_KEYS[provider]] = raw

    async def read(self, provider: str) -> dict[str, Any]:
        envelope = await self._load(provider)
        if not envelope:
            return {"models": [], "refreshed_at": None, "last_ok_at": None, "state": "unavailable", "error_kind": None, "stale": True}
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(envelope["refreshed_at"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = settings.llm_discovery_stale_ceiling_seconds + 1
        if age > settings.llm_discovery_stale_ceiling_seconds:
            return {**envelope, "models": [], "state": "unavailable", "stale": True}
        stale = age > settings.llm_discovery_fresh_ttl_seconds
        result = {**envelope, "stale": stale}
        if stale and provider not in _background:
            task = asyncio.create_task(self.refresh(provider))
            _background[provider] = task
            task.add_done_callback(lambda _: _background.pop(provider, None))
        return result


_discovery = ModelDiscovery()


async def refresh_models(provider: str | None = None) -> dict[str, str]:
    providers = [provider] if provider else list(PROVIDERS)
    return {p: await _discovery.refresh(p) for p in providers}


async def catalog() -> dict[str, Any]:
    per_provider = {p: await _discovery.read(p) for p in PROVIDERS}
    models = [
        m for p in per_provider.values() for m in p["models"]
        if m.get("status") == "available" and m.get("generation_methods")
    ]
    result = {"models": models, "providers": per_provider}
    raw = json.dumps(result, separators=(",", ":"))
    redis = get_redis()
    try:
        if redis is not None:
            await redis.set(CATALOG_KEY, raw, px=int(settings.llm_discovery_stale_ceiling_seconds * 1000))
        else:
            _memory[CATALOG_KEY] = raw
    except Exception:
        _memory[CATALOG_KEY] = raw
    return result
