"""Off-server destination contract for backups, plus a local directory implementation for tests and disposable drills.

`ObjectStore` is the whole surface a destination must provide (an S3-compatible adapter maps it onto PutObject, GetObject,
ListObjectsV2 and DeleteObject). No real adapter ships: choosing and funding a provider and supplying its credentials is an
owner decision outside this repository (see OPERATIONS.md). `LocalDirStore` is NOT off-server and says so.
"""
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")


class StoreError(Exception):
    pass


class ObjectStore(Protocol):
    """Keys are flat '/'-separated names. Objects are immutable: `put` never overwrites."""

    off_server: bool

    def put(self, key: str, source: Path) -> None: ...  # StoreError if the key exists
    def get(self, key: str, dest: Path) -> None: ...  # StoreError if missing
    def list(self, prefix: str = "") -> list[str]: ...  # sorted
    def delete(self, key: str) -> None: ...  # idempotent


def check_key(key: str) -> str:
    if not KEY_RE.fullmatch(key) or ".." in key:
        raise StoreError(f"invalid object key: {key!r}")
    return key


class LocalDirStore:
    off_server = False

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    def put(self, key: str, source: Path) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".partial-")
        os.close(fd)
        try:
            shutil.copyfile(source, tmp)
            os.link(tmp, target)  # atomic and fails if the key exists, so a half-written object is never visible
        except FileExistsError as exc:
            raise StoreError(f"object already exists: {key}") from exc
        except OSError as exc:
            raise StoreError(f"could not write object {key}: {exc.strerror}") from exc
        finally:
            Path(tmp).unlink(missing_ok=True)

    def get(self, key: str, dest: Path) -> None:
        try:
            shutil.copyfile(self._path(key), dest)
        except OSError as exc:
            raise StoreError(f"could not read object {key}: {exc.strerror}") from exc

    def list(self, prefix: str = "") -> list[str]:
        if not self.root.is_dir():
            return []
        keys = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file() and not p.name.startswith(".partial-"))
        return sorted(k for k in keys if k.startswith(prefix))

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


@dataclass(frozen=True)
class S3Settings:
    """The configuration an S3-compatible adapter needs. Secrets stay out of repr, logs and errors."""

    endpoint: str
    bucket: str
    prefix: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str = "auto"

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "S3Settings":
        def need(name: str) -> str:
            value = env.get(name, "").strip()
            if not value or value.startswith("replace-with"):
                raise StoreError(f"{name} is not set")
            return value

        endpoint = need("BACKUP_S3_ENDPOINT")
        parts = urlsplit(endpoint)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query:
            raise StoreError("BACKUP_S3_ENDPOINT must be a plain https URL without credentials or query")
        bucket = need("BACKUP_S3_BUCKET")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
            raise StoreError("BACKUP_S3_BUCKET is not a valid bucket name")
        prefix = env.get("BACKUP_S3_PREFIX", "postgres").strip("/")
        check_key(prefix)
        return cls(endpoint.rstrip("/"), bucket, prefix, need("BACKUP_S3_ACCESS_KEY_ID"), need("BACKUP_S3_SECRET_ACCESS_KEY"),
                   env.get("BACKUP_S3_REGION", "auto") or "auto")
