import hashlib
import json
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(payload: dict) -> str:
    """Stable hash of source-derived content, used to detect changes between runs."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
