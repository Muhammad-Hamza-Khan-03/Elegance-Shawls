from bson import ObjectId
from base64 import b64encode, b64decode
import json
from datetime import datetime


def encode_cursor(created_at: datetime, _id: ObjectId) -> str:
    payload = {
        "created_at": created_at.isoformat(),
        "_id": str(_id),
    }
    return b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> dict:
    try:
        decoded = json.loads(b64decode(cursor).decode())
        return {
            "created_at": datetime.fromisoformat(decoded["created_at"]),
            "_id": ObjectId(decoded["_id"]),
        }
    except Exception:
        raise ValueError("Invalid cursor")
