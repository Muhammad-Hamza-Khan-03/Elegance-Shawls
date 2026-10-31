"""Synthetic-only evaluator scaffolding for semantic retrieval (M2-S0/S1). No network, no production data.

  python evals/semantic_eval.py [--dataset evals/synthetic/semantic_retrieval.jsonl] [--release-ready]

Inputs must be explicitly synthetic ("synthetic": true, ids prefixed "syn-"); anything else is refused. Results from
the test-only fake provider are a harness check, never evidence. release_ready is true only with non-empty cases that
a human marked "reviewed": true, a non-test provider, and recall at or above the threshold. Exit: 0 ok, 2 refused input,
3 --release-ready requested but not ready.
"""
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "apps" / "backend"))

from semantic.embeddings import (ALLOWED_MODELS, TEST_ONLY_PROVIDERS, EmbeddingConfig,  # noqa: E402
                                 FakeEmbeddingProvider)
from semantic.representation import REPRESENTATION_VERSION, represent  # noqa: E402

DEFAULT_DATASET = HERE / "synthetic" / "semantic_retrieval.jsonl"
RECALL_AT_K, K, MIN_RECALL = "recall_at_3", 3, 0.80


class NonSyntheticInput(ValueError):
    pass


def load_cases(raw: bytes) -> list[dict]:
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    for c in cases:
        ids = [c.get("id"), *(p.get("id") for p in c.get("corpus", []))]
        if c.get("synthetic") is not True or not all(isinstance(i, str) and i.startswith("syn-") for i in ids):
            raise NonSyntheticInput(f"case {c.get('id')!r} is not marked synthetic with syn- ids")
    return cases


def _cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalised


def evaluate(cases: list[dict], provider, dataset_sha256: str = "") -> dict:
    # Keep the programmatic boundary as strict as the CLI loader: callers cannot
    # bypass the synthetic-only contract by constructing cases in memory.
    if any(
        c.get("synthetic") is not True
        or not all(
            isinstance(identifier, str) and identifier.startswith("syn-")
            for identifier in [c.get("id"), *(p.get("id") for p in c.get("corpus", []))]
        )
        for c in cases
    ):
        raise NonSyntheticInput("evaluation cases must be explicitly synthetic with syn- ids")
    cfg: EmbeddingConfig = provider.config
    hits = 0.0
    for c in cases:
        q = provider.embed(represent({"name": c["query"]})["text"])
        scored = sorted(((-_cosine(q, provider.embed(represent(p)["text"])), p["id"]) for p in c["corpus"]))
        top = {pid for _, pid in scored[:K]}
        hits += len(top & set(c["relevant"])) / len(c["relevant"])
    recall = hits / len(cases) if cases else None
    reviewed = bool(cases) and all(c.get("reviewed") is True for c in cases)
    test_only = cfg.provider in TEST_ONLY_PROVIDERS
    reasons = [r for r, bad in (("no cases (empty evaluation)", not cases),
                                ("cases not human-reviewed", bool(cases) and not reviewed),
                                ("test-only fake provider is not evidence", test_only)) if bad]
    ready = not reasons and recall is not None and recall >= MIN_RECALL
    if not reasons and not ready:
        reasons.append(f"{RECALL_AT_K}={recall:.3f} < {MIN_RECALL}")
    return {
        "status": "PASS" if ready else "NOT_EVALUATED" if reasons and (test_only or not cases or not reviewed) else "FAIL",
        "release_ready": ready,
        "reasons": reasons,
        "metrics": {RECALL_AT_K: recall},
        "reproducibility": {
            "representation_version": REPRESENTATION_VERSION,
            "provider": cfg.provider, "model": cfg.model, "dimensions": cfg.dimensions,
            "k": K, "cases": len(cases), "dataset_sha256": dataset_sha256,
            "python": platform.python_version(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--release-ready", action="store_true")
    args = parser.parse_args(argv)
    path = args.dataset.resolve()
    if path.parent != (HERE / "synthetic").resolve():
        print("refused: datasets must live in evals/synthetic/", file=sys.stderr)
        return 2
    raw = path.read_bytes() if path.is_file() else b""
    try:
        cases = load_cases(raw)
    except NonSyntheticInput as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    # Only the allowlisted fake exists in this slice; live providers arrive with their own reviewed change.
    (provider_name, model), dims = next(iter(ALLOWED_MODELS.items()))
    provider = FakeEmbeddingProvider(EmbeddingConfig(provider_name, model, dims))
    report = evaluate(cases, provider, hashlib.sha256(raw).hexdigest())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 3 if args.release_ready and not report["release_ready"] else 0


if __name__ == "__main__":
    sys.exit(main())
