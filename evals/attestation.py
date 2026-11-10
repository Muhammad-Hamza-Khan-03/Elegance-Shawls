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

Not covered by the leakage check: invisible characters inside a word (zero-width space, soft hyphen), look-alike letters from other
scripts, other digit scripts, files that are not lowercase `*.jsonl` (.json, .csv, .yaml, uppercase extensions), symlinked
directories, and strings under keys not in QUERY_FIELDS.

Any error while verifying a record or checking datasets (bad JSON, wrong shapes, odd characters, unreadable or hostile files) is
caught and reported as a verification failure: the gate fails closed. The catch is deliberately broad (Exception); it is a safety net,
not a reason to feed the verifier hostile files.
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
        # bytes comparison: str arguments to compare_digest must be ASCII and raise otherwise
        verified = isinstance(payload, dict) and isinstance(signature, str) \
            and hmac.compare_digest(sign(payload, key).encode("ascii"), signature.encode("utf-8"))
    except Exception:    # noqa: BLE001 - hostile or malformed record of any kind (bad JSON, lone surrogates, deep nesting): fail closed
        return None, f"{path.name}: malformed record"
    if not verified:
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
    try:
        same_hash = dataset.is_file() and payload["dataset_sha256"] == sha256_file(dataset)
    except OSError:
        same_hash = False
    if not same_hash:
        problems.append("dataset content differs from the attested sha256")
    if payload["split"] != "held_out":
        problems.append(f"split is {payload['split']!r}, release evidence must be held_out")
    if _norm(payload["author"]) == _norm(payload["reviewer"]):
        problems.append("reviewer is the dataset author, review is not independent")
    if not problems:
        try:
            problems += [f"held-out leakage, {leak}" for leak in leakage(root, suite_cfg["dataset"])]
        except Exception as error:   # noqa: BLE001 - unreadable, malformed or hostile dataset (symlink loop, deep nesting...): fail closed
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
    try:
        current = candidate_digest(root)
    except OSError:
        return ["approval.json: candidate files could not be read"]
    if payload["candidate_digest"] != current:
        return ["approval.json: approved a different candidate (thresholds, profile, manifest or attestations changed)"]
    return []
