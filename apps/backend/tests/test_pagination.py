"""UUID keyset cursors: round trip, ordering key, and strict rejection of anything malformed or tampered."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from utils.pagination import MAX_LENGTH, decode_cursor, encode_cursor

AT = datetime(2026, 10, 29, 12, 30, 45, 123456, tzinfo=timezone.utc)
ID = uuid.UUID("0b0e5c6e-5b7a-4c2e-9a2f-1d3e4f5a6b7c")


def forged(payload: dict, checksum: str | None = None) -> str:
    """A syntactically complete cursor around arbitrary content (with the right checksum unless one is given)."""
    from utils.pagination import _checksum

    raw = json.dumps(payload, separators=(",", ":")).encode()
    return f"{base64.urlsafe_b64encode(raw).decode().rstrip('=')}.{checksum or _checksum(raw)}"


def test_round_trip_preserves_microseconds_and_the_uuid():
    assert decode_cursor(encode_cursor(AT, ID)) == (AT, ID)


def test_other_timezones_are_normalised_to_utc():
    plus5 = datetime(2026, 10, 29, 17, 30, 45, 123456, tzinfo=timezone(timedelta(hours=5)))
    assert decode_cursor(encode_cursor(plus5, ID)) == (AT, ID)


def test_cursors_are_url_safe_and_opaque():
    cursor = encode_cursor(AT, ID)
    assert all(c.isalnum() or c in "-_." for c in cursor)
    assert str(ID) not in cursor and len(cursor) < MAX_LENGTH


def test_naive_datetimes_cannot_be_encoded():
    with pytest.raises(ValueError):
        encode_cursor(datetime(2026, 1, 1), ID)


def test_different_positions_give_different_cursors():
    assert encode_cursor(AT, ID) != encode_cursor(AT + timedelta(microseconds=1), ID)
    assert encode_cursor(AT, ID) != encode_cursor(AT, uuid.UUID(int=ID.int + 1))


@pytest.mark.parametrize("bad", [
    "", ".", "garbage", "not.valid.at.all", "e30", "e30.", ".abc", "!!!!.0000", "e30.000000000000",
    "A" * (MAX_LENGTH + 1), None, 123, b"bytes",
])
def test_malformed_cursors_are_rejected(bad):
    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_cursor(bad)


def test_the_old_objectid_cursor_format_is_rejected():
    legacy = base64.b64encode(json.dumps({"created_at": AT.isoformat(), "_id": "507f1f77bcf86cd799439011"}).encode()).decode()
    with pytest.raises(ValueError):
        decode_cursor(legacy)


def test_any_edit_to_a_valid_cursor_is_rejected():
    cursor = encode_cursor(AT, ID)
    body, _, check = cursor.partition(".")
    edits = {
        "flipped body char": ("B" if body[5] != "B" else "C").join([body[:5], body[6:]]) + "." + check,
        "wrong checksum": body + "." + "0" * 12,
        "missing checksum": body,
        "truncated": cursor[:-1],
        "extra segment": cursor + ".x",
        "swapped halves": check + "." + body,
    }
    for name, tampered in edits.items():
        with pytest.raises(ValueError):
            decode_cursor(tampered)
        assert name


@pytest.mark.parametrize("payload", [
    {"v": 1, "c": AT.isoformat(), "i": str(ID), "extra": 1},          # unknown key
    {"v": 2, "c": AT.isoformat(), "i": str(ID)},                      # unknown version
    {"v": 1, "c": AT.isoformat()},                                    # missing id
    {"v": 1, "c": "2026-10-29T12:00:00", "i": str(ID)},               # naive timestamp
    {"v": 1, "c": "yesterday", "i": str(ID)},
    {"v": 1, "c": AT.isoformat(), "i": "507f1f77bcf86cd799439011"},   # not a UUID
    {"v": 1, "c": AT.isoformat(), "i": ID.hex},                       # a UUID, but not in canonical form
    {"v": 1, "c": AT.isoformat(), "i": 5},
    [1, 2, 3], "text", 7,
])
def test_validly_signed_but_wrong_content_is_rejected(payload):
    with pytest.raises(ValueError):
        decode_cursor(forged(payload))


def test_ordering_key_matches_the_database_ordering_semantics():
    keys = sorted([(AT, uuid.UUID(int=2)), (AT, uuid.UUID(int=1)), (AT + timedelta(seconds=1), uuid.UUID(int=0))], reverse=True)
    assert [decode_cursor(encode_cursor(*k)) for k in keys] == keys           # round trip keeps (created_at, id) order
