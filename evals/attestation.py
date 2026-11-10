"""Verifiable evidence and approval for the release gate (nothing here is a YAML flag).

`evals/attestations/<suite>.json` is an independent review record and `evals/approval.json` an owner approval. Both are
{"payload": {...}, "signature": hex HMAC-SHA256 of the canonical payload}. The keys come ONLY from the environment of whoever runs
the check (EVAL_REVIEWER_KEY, EVAL_OWNER_KEY, at least 32 characters, never committed); without them nothing verifies and the gate
stays closed. Editing a file in the repository therefore cannot make a suite "reviewed" or record an approval.

What this proves: the holder of the reviewer key signed this exact dataset hash as a held-out split with a reviewer different from
the author, nothing in it overlaps another dataset, and the holder of the owner key approved this exact candidate (thresholds,
profile, manifest, attestations). What it does NOT prove: that a human really reviewed the labels (that is the review workflow,
issue #139), nor protect against a leaked or shared key. The keys are symmetric: whoever can verify can also sign, so the keys must
stay with the reviewer and the owner and must differ. There is no key rotation or revocation; change the key to invalidate all records.

Identity limits: `author` and `reviewer` are free text INSIDE the signed payload. The signature proves a holder of the reviewer key
wrote them, not that they name different people, nor that either name is real. The independence check only compares the two
strings after Unicode NFKC, case folding and whitespace collapsing; "Alice" and "Alice B." pass as different. Real independence
rests on who holds the reviewer key and on the human review workflow (#139), not on this code.

Leakage limits: the check normalises (NFKC, case folding, punctuation and whitespace collapsed) every string found under the keys
in QUERY_FIELDS, at any nesting depth and inside lists, in every `*.jsonl` file below datasets/ other than the attested one. It
does not look at other directories (recorded/, fixtures/, code, vocabularies), at paraphrases, or at other keys. It is a best-effort
guard against accidental reuse, not proof of independence.

Malformed input (bad JSON, wrong shapes, non-ASCII signatures, rows that are not objects) is a verification failure, never an exception.
"""
import hashlib
import hmac
import json
import re
import unicodedata
from pathlib import Path

REVIEWER_KEY_ENV, OWNER_KEY_ENV = "EVAL_REVIEWER_KEY", "EVAL_OWNER_KEY"
MIN_KEY_LENGTH = 32
QUERY_FIELDS = ("query", "q", "text", "transcript", "utterance", "input", "prompt", "question")
REVIEW_FIELDS = {"suite", "dataset", "dataset_sha256", "split", "author", "reviewer", "reviewed_at"}
APPROVAL_FIELDS = {"owner", "candidate_digest", "approved_at"}


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign(payload: dict, key: str) -> str:
    return hmac.new(key.encode("utf-8"), canonical(payload), hashlib.sha256).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_signed(path: Path, key: str | None, key_env: str, fields: set[str]) -> tuple[dict | None, str | None]:
    """(payload, problem). The signature is checked before any content is trusted."""
    if not path.is_file():
        return None, f"{path.name}: no record"
    if not key or len(key) < MIN_KEY_LENGTH:
        return None, f"{path.name}: cannot verify, {key_env} is not set (at least {MIN_KEY_LENGTH} characters)"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        payload, signature = record["payload"], record["signature"]
    except (ValueError, KeyError, TypeError):
        return None, f"{path.name}: malformed record"
    # bytes comparison: str arguments to compare_digest must be ASCII and raise otherwise
    if not isinstance(payload, dict) or not isinstance(signature, str) \
            or not hmac.compare_digest(sign(payload, key).encode("ascii"), signature.encode("utf-8")):
        return None, f"{path.name}: signature does not verify"
    if set(payload) != fields or any(not isinstance(payload[f], str) or not payload[f].strip() for f in fields):
        return None, f"{path.name}: payload must have exactly {sorted(fields)}, all non-empty text"
    return payload, None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def _norm_query(text: str) -> str:
    return re.sub(r"[\W_]+", " ", _norm(text)).strip()      # punctuation and spacing differences do not make a query "new"


def _walk(value, found: set[str], in_field: bool = False) -> None:
    if isinstance(value, str):
        if in_field and (q := _norm_query(value)):
            found.add(q)
    elif isinstance(value, list):
        for item in value:
            _walk(item, found, in_field)
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk(item, found, in_field or key in QUERY_FIELDS)


def queries(path: Path) -> set[str]:
    """Normalised query strings of a JSONL file. Raises ValueError on anything that is not one JSON object per line."""
    out: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{number}: row is not a JSON object")
            _walk(row, out)
    return out


def leakage(root: Path, dataset: str) -> list[str]:
    """Normalised queries of `dataset` that also occur in any OTHER dataset under datasets/ (train/dev/other eval data)."""
    held = queries(root / dataset)
    leaked = []
    for other in sorted((root / "datasets").rglob("*.jsonl")):
        if other.resolve() != (root / dataset).resolve():
            leaked += [f"{other.relative_to(root)}: {q!r}" for q in sorted(held & queries(other))]
    return leaked


def review_problems(root: Path, suite: str, suite_cfg: dict, env: dict) -> list[str]:
    """Why this suite's dataset is not independently reviewed, leakage-free held-out evidence (empty = it is)."""
    path = root / "attestations" / f"{suite}.json"
    payload, problem = _load_signed(path, env.get(REVIEWER_KEY_ENV), REVIEWER_KEY_ENV, REVIEW_FIELDS)
    if problem:
        return [problem]
    dataset = root / suite_cfg["dataset"]
    problems = []
    if payload["suite"] != suite or payload["dataset"] != suite_cfg["dataset"]:
        problems.append("attestation is for a different suite or dataset")
    if not dataset.is_file() or payload["dataset_sha256"] != sha256_file(dataset):
        problems.append("dataset content differs from the attested sha256")
    if payload["split"] != "held_out":
        problems.append(f"split is {payload['split']!r}, release evidence must be held_out")
    if _norm(payload["author"]) == _norm(payload["reviewer"]):
        problems.append("reviewer is the dataset author, review is not independent")
    if not problems:
        try:
            problems += [f"held-out leakage, {leak}" for leak in leakage(root, suite_cfg["dataset"])]
        except (ValueError, OSError) as error:           # unreadable or malformed dataset: fail closed, never raise
            problems.append(f"dataset could not be checked for leakage ({error})")
    return problems


def candidate_digest(root: Path) -> str:
    """One hash over everything an approval covers: gate configuration, frozen manifest and every attestation."""
    names = ["thresholds.yaml", "release_profile.yaml", "artifact_manifest.json",
             *(f"attestations/{p.name}" for p in sorted((root / "attestations").glob("*.json")))]
    return hashlib.sha256(canonical({n: sha256_file(root / n) for n in names if (root / n).is_file()})).hexdigest()


def approval_problems(root: Path, env: dict) -> list[str]:
    payload, problem = _load_signed(root / "approval.json", env.get(OWNER_KEY_ENV), OWNER_KEY_ENV, APPROVAL_FIELDS)
    if problem:
        return [problem]
    if env.get(OWNER_KEY_ENV) == env.get(REVIEWER_KEY_ENV):
        return ["approval.json: owner and reviewer keys must differ"]
    if payload["candidate_digest"] != candidate_digest(root):
        return ["approval.json: approved a different candidate (thresholds, profile, manifest or attestations changed)"]
    return []
