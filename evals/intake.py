"""Intake guard for real customer queries (issue #139, slice 2b). Collection is BLOCKED, so this refuses to load anything.

While evals/real_queries_status.md says "Status: BLOCKED" (or is missing), `load_real_queries` raises Blocked and reads nothing. Once
the owner has deliberately changed that status, rows must be explicitly scrubbed and carry a consent reference. The scrub patterns
are a safety net against obvious personal data, not a guarantee: a human must still check the scrubbed text.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATTERNS = {
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "link": re.compile(r"(?i)(https?://|www\.|wa\.me/)\S+"),
    "phone number": re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)"),
    "long digit run": re.compile(r"\d{6,}"),
    "enquiry reference": re.compile(r"\bES-[A-Z0-9]{6}\b", re.I),
    "handle": re.compile(r"(?<!\w)@\w{3,}"),
}


class Blocked(Exception):
    """Real-query collection is not unblocked."""


def is_blocked(root: Path = HERE) -> bool:
    status = root / "real_queries_status.md"
    return not status.is_file() or "Status: BLOCKED" in status.read_text(encoding="utf-8")


def scrub_problems(text: str) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def load_real_queries(path: Path, root: Path = HERE) -> list[dict]:
    """Rows {"query", "consent_ref", "source": "real"}. Raises Blocked while blocked; ValueError (never echoing the text) on any problem."""
    if is_blocked(root):
        raise Blocked("real-query collection is BLOCKED (evals/real_queries_status.md); nothing was read")
    rows, seen = [], set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or row.get("source") != "real" or not isinstance(row.get("query"), str) or not row["query"].strip() \
                or not isinstance(row.get("consent_ref"), str) or not row["consent_ref"].strip():
            raise ValueError(f"line {number}: needs source 'real', a non-empty query and a consent_ref")
        if found := scrub_problems(row["query"]):
            raise ValueError(f"line {number}: looks like it still contains personal data ({', '.join(found)}); scrub it first")
        key = " ".join(row["query"].casefold().split())
        if key in seen:
            raise ValueError(f"line {number}: duplicate query")
        seen.add(key)
        rows.append(row)
    return rows
