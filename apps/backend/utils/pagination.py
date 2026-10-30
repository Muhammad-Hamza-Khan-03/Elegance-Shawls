"""Opaque keyset cursors over (created_at, id) for UUID-keyed tables.

A cursor is `<base64url(json)>.<checksum>`. The checksum is not a secret: it makes truncated or
hand-edited tokens fail deterministically instead of silently jumping to a different position.
Anything that does not decode to exactly one valid position raises ValueError (callers answer 400).
"""
import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

VERSION = 1
MAX_LENGTH = 512
Key = tuple[datetime, uuid.UUID]


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(b"elegance-cursor-v1:" + payload).hexdigest()[:12]


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    payload = json.dumps(
        {"v": VERSION, "c": created_at.astimezone(timezone.utc).isoformat(timespec="microseconds"), "i": str(row_id)},
        separators=(",", ":"),
    ).encode()
    return f"{base64.urlsafe_b64encode(payload).decode().rstrip('=')}.{_checksum(payload)}"


def decode_cursor(cursor: str) -> Key:
    try:
        if not isinstance(cursor, str) or not cursor or len(cursor) > MAX_LENGTH:
            raise ValueError
        body, dot, checksum = cursor.partition(".")
        if not dot or "." in checksum:
            raise ValueError
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(checksum, _checksum(payload)):
            raise ValueError
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {"v", "c", "i"} or data["v"] != VERSION:
            raise ValueError
        created_at = datetime.fromisoformat(data["c"])
        row_id = uuid.UUID(data["i"])
        if created_at.tzinfo is None or str(row_id) != data["i"]:
            raise ValueError
        return created_at.astimezone(timezone.utc), row_id
    except Exception as exc:  # any malformed input, whatever the cause, is one error to callers
        raise ValueError("Invalid cursor") from exc
