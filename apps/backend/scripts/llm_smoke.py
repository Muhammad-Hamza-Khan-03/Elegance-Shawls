"""Smoke test for the LLM gateway. Prints model, tokens, cost and latency; never prints keys.

  python scripts/llm_smoke.py --fake          # no network, no keys
  python scripts/llm_smoke.py                 # uses LLM_CHAIN_DEFAULT and provider keys from the environment
Run from apps/backend.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from configuration.config import settings  # noqa: E402
from llm.gateway import LLMError, LLMGateway  # noqa: E402

KEY_ENV = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="use the built-in fake provider")
    parser.add_argument("--personal", action="store_true", help="route as personal data (production chain)")
    args = parser.parse_args()
    if args.fake:
        settings.llm_chain_default = settings.llm_production_chain = "fake/model"
    chain = [m for m in (settings.llm_production_chain if args.personal else settings.llm_chain_default).split(",") if m]
    import importlib.util

    from llm.openai_compatible import supports

    needs_litellm = [m for m in chain if not args.fake and not supports(m) and not m.startswith("fake/")]
    if needs_litellm and importlib.util.find_spec("litellm") is None:
        print(f"BLOCKED: {', '.join(needs_litellm)} need litellm (pip install -r requirements-llm.txt)")
        return 2
    for model in chain:
        env = KEY_ENV.get(model.split("/", 1)[0])
        if env:  # presence only, never the value
            print(f"{model}: {env} {'is set' if os.environ.get(env) else 'is NOT set'}")
    try:
        result = await LLMGateway().complete([{"role": "user", "content": "Reply with the single word: ok"}],
                                             personal=args.personal)
    except LLMError as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"OK model={result.model} attempts={result.attempts} tokens={result.input_tokens}/{result.output_tokens} "
          f"cost_usd={result.cost_usd:.6f} latency_ms={result.latency_ms}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
