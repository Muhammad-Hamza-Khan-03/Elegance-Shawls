"""Gated live-provider smoke for enrichment. Refuses unless every gate is explicitly set; uses ONLY the synthetic fixture.

  P1_S3_PROVIDER_SMOKE=1 P1_S3_SYNTHETIC_ONLY=1 P1_S3_PROVIDER=groq|gemini P1_S3_MODEL=<upstream model> \
      python scripts/enrichment_provider_smoke.py

No fallback chain, no database, at most 2 provider calls, spend capped at COST_CAP_USD. Prints status counts only:
never keys, prompts or provider responses. Run from apps/backend.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from enrichment.service import generate, prepare  # noqa: E402
from llm.gateway import BudgetExceededError  # noqa: E402
from llm.openai_compatible import openai_compatible_completion  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "enrichment" / "synthetic_product.json"
PROVIDERS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
COST_CAP_USD = 0.02
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")


class GateError(Exception):
    pass


def check_gate(env) -> tuple[str, str]:
    """-> (provider, model) or GateError. Every switch must be explicit; nothing has a default."""
    if env.get("P1_S3_PROVIDER_SMOKE") != "1":
        raise GateError("P1_S3_PROVIDER_SMOKE=1 is required")
    if env.get("P1_S3_SYNTHETIC_ONLY") != "1":
        raise GateError("P1_S3_SYNTHETIC_ONLY=1 is required")
    provider, model = env.get("P1_S3_PROVIDER", ""), env.get("P1_S3_MODEL", "")
    if provider not in PROVIDERS:
        raise GateError("P1_S3_PROVIDER must be groq or gemini")
    if not _MODEL.fullmatch(model):
        raise GateError("P1_S3_MODEL must be set explicitly")
    if not env.get(PROVIDERS[provider]):
        raise GateError(f"{PROVIDERS[provider]} is not set")  # names the variable, never a value
    return provider, model


def load_fixture(path: Path = FIXTURE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True or not str(data.get("id", "")).startswith("synthetic-"):
        raise GateError("fixture is not marked synthetic")
    return data["product"]


class CappedBudget:
    """Local spend ledger (no Redis): blocks the next call once the cap is spent."""

    def __init__(self, cap: float):
        self.cap, self.spent = cap, 0.0

    async def check(self) -> None:
        if self.spent >= self.cap:
            raise BudgetExceededError("smoke budget is spent")

    async def record(self, cost: float) -> bool:
        self.spent += cost
        return False


async def run(env, complete=None) -> int:
    try:
        provider, model = check_gate(env)
        product = load_fixture()
    except GateError as exc:
        print(f"REFUSED: {exc}")
        return 2
    payload, _ = prepare(product)
    budget = CappedBudget(COST_CAP_USD)
    result = await generate(complete or openai_compatible_completion, f"{provider}/{model}", payload, budget=budget,
                            log_id="smoke")
    values = (result.suggestions or {}).values()
    print(f"{result.status.upper()} provider={provider} attempts={result.attempts} fields={len(values)} "
          f"null_fields={sum(v['value'] is None for v in values)} validation_errors={len(result.validation_errors)} "
          f"error={result.last_error or '-'} cost_usd={budget.spent:.6f}")
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run(os.environ)))
