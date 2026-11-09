"""Deterministic integrity check for the frozen evaluation artifacts (replaces tests that shelled out to `git diff c71ef03`).

  python evals/artifact_manifest.py            # verify; exit 1 on drift
  python evals/artifact_manifest.py --write    # regenerate artifact_manifest.json (a deliberate, reviewable change)

Frozen files are gold data and thresholds that earlier results were measured against. A change is allowed, but it must be
visible in review as a manifest change with its reason, never silent. `thresholds.yaml` is deliberately NOT frozen: it is the gate.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "artifact_manifest.json"
FROZEN = ["datasets/embedding_synthetic.jsonl", "embedding_thresholds.yaml", "datasets/filter_parsing.jsonl",
          "datasets/retrieval_constraints.jsonl", "datasets/retrieval_hybrid.jsonl"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path = HERE) -> list[str]:
    """Problems found (empty = every frozen artifact matches the manifest)."""
    recorded = json.loads((root / "artifact_manifest.json").read_text(encoding="utf-8"))["sha256"]
    problems = [f"{rel}: not in the manifest" for rel in FROZEN if rel not in recorded]
    for rel, expected in recorded.items():
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: missing")
        elif digest(path) != expected:
            problems.append(f"{rel}: content changed (sha256 {digest(path)[:12]} != {expected[:12]})")
    return problems


def write(root: Path = HERE) -> None:
    payload = {"note": "SHA-256 of frozen evaluation artifacts; regenerate only with a stated reason (python evals/artifact_manifest.py --write)",
               "sha256": {rel: digest(root / rel) for rel in FROZEN}}
    (root / "artifact_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--write" in sys.argv:
        write()
        print("wrote", MANIFEST)
        sys.exit(0)
    found = verify()
    for problem in found:
        print("DRIFT:", problem)
    print("artifact manifest: " + ("OK" if not found else f"{len(found)} problem(s)"))
    sys.exit(1 if found else 0)
