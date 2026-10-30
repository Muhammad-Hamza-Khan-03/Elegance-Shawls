"""Encrypted PostgreSQL backup, verification, retention, freshness check and disposable restore drill.

Everything runs the stock PostgreSQL client tools (pg_dump, pg_restore, psql) without a shell. Connection details travel in
libpq environment variables, never argv, so secrets are not visible in `ps`; the tools are looked up through PG_DUMP_CMD,
PG_RESTORE_CMD and PSQL_CMD (default: the bare tool name) so they can be wrapped, for example to run inside the compose
`postgres` container (deploy/postgres/container-pg.sh). Nothing here chooses, configures or contacts a real destination.
"""
import json
import os
import re
import shlex
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote, urlsplit

from backup import crypto
from backup.store import ObjectStore, StoreError

EXIT_CODES = {"config": 2, "dump": 3, "verify": 4, "store": 5, "retention": 6, "stale": 7, "drill": 8, "role": 9}
TOOL_ENV = {"pg_dump": "PG_DUMP_CMD", "pg_restore": "PG_RESTORE_CMD", "psql": "PSQL_CMD"}
STEM_RE = re.compile(r"^(?P<prefix>.+)/elegance-(?P<ts>\d{8}T\d{6}Z)\.manifest\.json$")
DRILL_DB_RE = re.compile(r"^restore_drill_[a-z0-9_]{1,40}$")
LOOPBACK = {"", "localhost", "127.0.0.1", "::1"}
TOOL_TIMEOUT = 3600


class BackupError(Exception):
    """`code` selects the CLI exit status (EXIT_CODES); `message` is already free of secrets."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def redact(text: str, secrets=()) -> str:
    for secret in filter(None, secrets):
        text = text.replace(secret, "***")
    return re.sub(r"(\w+://[^:/\s@]*):[^@\s]*@", r"\1:***@", text)


@dataclass(frozen=True)
class PgConn:
    host: str
    port: str
    user: str
    password: str = field(repr=False)
    dbname: str

    @classmethod
    def from_url(cls, url: str, name: str) -> "PgConn":
        try:
            parts = urlsplit(url)
            port = str(parts.port or "")
        except ValueError:
            raise BackupError("config", f"{name} is not a valid postgresql:// URL") from None
        dbname = unquote(parts.path.lstrip("/"))
        if parts.scheme not in ("postgresql", "postgres") or not parts.username or not dbname or parts.query:
            raise BackupError("config", f"{name} must look like postgresql://user:password@host:port/database (no query string)")
        return cls(parts.hostname or "", port, unquote(parts.username), unquote(parts.password or ""), dbname)

    def env(self, base: Mapping[str, str]) -> dict[str, str]:
        # Strip our own and libpq variables so the tools never see the encryption passphrase or a stray PGSERVICE.
        clean = {k: v for k, v in base.items() if not k.startswith(("BACKUP_", "RESTORE_DRILL_", "PG"))}
        return {**clean, "PGHOST": self.host, "PGPORT": self.port, "PGUSER": self.user, "PGPASSWORD": self.password,
                "PGDATABASE": self.dbname, "PGCONNECT_TIMEOUT": "10"}


def read_secret(env: Mapping[str, str], name: str) -> str:
    """NAME_FILE (a path from the deployment secret manager, owner-only) wins over NAME."""
    path = env.get(f"{name}_FILE")
    if not path:
        value = env.get(name, "")
    else:
        try:
            if os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise BackupError("config", f"{name}_FILE must not be readable by group or others")
            value = Path(path).read_text().strip("\r\n")
        except OSError as exc:
            raise BackupError("config", f"{name}_FILE cannot be read: {exc.strerror}") from None
    if not value:
        raise BackupError("config", f"{name} (or {name}_FILE) is not set")
    return value


def run_tool(tool: str, conn: PgConn, args: list[str], *, code: str, env: Mapping[str, str] = os.environ,
             stdin: Path | None = None, stdout: Path | None = None, secrets=()) -> str:
    cmd = shlex.split(env.get(TOOL_ENV[tool], tool)) + args
    sink = os.open(stdout, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) if stdout else subprocess.PIPE
    try:
        with (stdin.open("rb") if stdin else open(os.devnull, "rb")) as source:
            proc = subprocess.run(cmd, env=conn.env(env), stdin=source, stdout=sink, stderr=subprocess.PIPE,
                                  timeout=TOOL_TIMEOUT, check=False)
    except FileNotFoundError:
        raise BackupError("config", f"{cmd[0]} is not installed (or set {TOOL_ENV[tool]})") from None
    except subprocess.TimeoutExpired:
        raise BackupError(code, f"{tool} timed out after {TOOL_TIMEOUT}s") from None
    finally:
        if stdout:
            os.close(sink)
    if proc.returncode != 0:
        tail = redact(proc.stderr.decode(errors="replace").strip()[-500:], (conn.password, *secrets))
        raise BackupError(code, f"{tool} failed (exit {proc.returncode}): {tail}")
    return "" if stdout else proc.stdout.decode(errors="replace").strip()


def psql(conn: PgConn, sql: str, *, code: str, env: Mapping[str, str] = os.environ) -> list[list[str]]:
    out = run_tool("psql", conn, ["-X", "-A", "-t", "-w", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql], code=code, env=env)
    return [line.split("|") for line in out.splitlines()]


# --- least privilege -------------------------------------------------------------------------------------------------

ROLE_SQL = """select r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls,
  has_database_privilege(current_user, current_database(), 'CREATE'),
  has_schema_privilege(current_user, 'public', 'CREATE'),
  pg_has_role(current_user, 'pg_read_all_data', 'MEMBER'),
  pg_has_role(current_user, 'pg_write_all_data', 'MEMBER'),
  (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p') and has_table_privilege(current_user, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'))
from pg_roles r where r.rolname = current_user"""
ROLE_MUST_BE_FALSE = ("superuser", "createdb", "createrole", "replication", "bypassrls", "CREATE on the database",
                      "CREATE on schema public")


def role_violations(row: list[str]) -> list[str]:
    """Empty list means the connected role matches the contract: read-only, member of pg_read_all_data, nothing else."""
    if len(row) != 10:
        return ["role could not be inspected"]
    flags = [v == "t" for v in row[:9]]
    found = [name for name, on in zip(ROLE_MUST_BE_FALSE, flags) if on]
    if not flags[7]:
        found.append("not a member of pg_read_all_data")
    if flags[8]:
        found.append("member of pg_write_all_data")
    if row[9] != "0":
        found.append(f"can write to {row[9]} public table(s)")
    return found


def require_backup_role(conn: PgConn, env: Mapping[str, str]) -> None:
    rows = psql(conn, ROLE_SQL, code="role", env=env)
    problems = role_violations(rows[0] if rows else [])
    if problems:
        raise BackupError("role", f"refusing to back up as {conn.user!r}, not a least-privilege backup role: " + "; ".join(problems))


# --- backup, verify -------------------------------------------------------------------------------------------------

@contextmanager
def private_dir(base: str | None):
    with tempfile.TemporaryDirectory(prefix="es-backup-", dir=base) as tmp:  # mkdtemp is 0700
        yield Path(tmp)


def stem_for(prefix: str, when: datetime) -> str:
    return f"{prefix}/elegance-{when.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"


def schema_snapshot(conn: PgConn, env: Mapping[str, str]) -> dict:
    tables = [r[0] for r in psql(conn, "select tablename from pg_tables where schemaname = 'public' order by 1", code="dump", env=env)]
    version = None
    if "alembic_version" in tables:
        rows = psql(conn, "select version_num from public.alembic_version", code="dump", env=env)
        version = rows[0][0] if rows else None
    return {"tables": tables, "alembic_version": version}


@dataclass
class BackupResult:
    stem: str
    manifest: dict
    pruned: list[str]
    retention_error: str | None = None


def create_backup(conn: PgConn, passphrase: str, store: ObjectStore, *, prefix: str = "postgres", keep_daily: int = 14,
                  keep_weekly: int = 8, work_dir: str | None = None, env: Mapping[str, str] = os.environ,
                  now: datetime | None = None) -> BackupResult:
    """Dump, encrypt, verify locally, upload (data first, manifest last), re-verify from the store, then apply retention.

    Retention only ever runs after a verified new backup, so a failing job never ages out the last good copies.
    """
    now = now or datetime.now(timezone.utc)
    try:
        crypto.check_passphrase(passphrase)
    except crypto.CryptoError as exc:
        raise BackupError("config", str(exc)) from None
    require_backup_role(conn, env)
    stem = stem_for(prefix, now)
    secrets = (passphrase,)
    with private_dir(work_dir) as tmp:
        plain, cipher = tmp / "dump.pgdump", tmp / "dump.enc"
        version = run_tool("pg_dump", conn, ["--version"], code="dump", env=env)
        run_tool("pg_dump", conn, ["--format=custom", "--no-password", "--lock-wait-timeout=30s"], code="dump", env=env, stdout=plain, secrets=secrets)
        if plain.stat().st_size == 0:
            raise BackupError("dump", "pg_dump produced an empty archive")
        run_tool("pg_restore", conn, ["--list"], code="dump", env=env, stdin=plain, stdout=tmp / "toc.txt")
        manifest = {"format": "pg_dump-custom", "version": 1, "database": conn.dbname, "created_at": now.isoformat(),
                    "pg_dump": version, **schema_snapshot(conn, env)}
        try:
            manifest = crypto.encrypt_file(plain, cipher, passphrase, manifest)
            crypto.decrypt_file(cipher, tmp / "roundtrip.pgdump", passphrase, manifest)  # prove we can read it back
        except crypto.CryptoError as exc:
            raise BackupError("verify", str(exc)) from None
        plain.unlink()
        (tmp / "roundtrip.pgdump").unlink()
        manifest_path = tmp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        try:
            store.put(f"{stem}.pgdump.enc", cipher)
            try:
                store.put(f"{stem}.manifest.json", manifest_path)
            except StoreError:
                store.delete(f"{stem}.pgdump.enc")
                raise
        except StoreError as exc:
            raise BackupError("store", redact(str(exc), secrets)) from None
        verify_backup(store, stem, passphrase, work_dir=work_dir, conn=conn, env=env)
    pruned, retention_error = [], None
    try:
        pruned = prune(store, prefix, keep_daily, keep_weekly)
    except (BackupError, StoreError) as exc:
        retention_error = redact(str(exc), secrets)
    return BackupResult(stem, manifest, pruned, retention_error)


def fetch_manifest(store: ObjectStore, stem: str, tmp: Path) -> dict:
    try:
        store.get(f"{stem}.manifest.json", tmp / "manifest.json")
        return json.loads((tmp / "manifest.json").read_text())
    except StoreError as exc:
        raise BackupError("store", str(exc)) from None
    except ValueError:
        raise BackupError("verify", f"manifest for {stem} is not valid JSON") from None


def verify_backup(store: ObjectStore, stem: str, passphrase: str, *, conn: PgConn, work_dir: str | None = None,
                  env: Mapping[str, str] = os.environ, decrypted_to: Path | None = None) -> dict:
    """Downloads, authenticates (MAC + digests), decrypts and parses the archive's table of contents with pg_restore --list."""
    with private_dir(work_dir) as tmp:
        manifest = fetch_manifest(store, stem, tmp)
        try:
            store.get(f"{stem}.pgdump.enc", tmp / "dump.enc")
            plain = decrypted_to or tmp / "dump.pgdump"
            crypto.decrypt_file(tmp / "dump.enc", plain, passphrase, manifest)
        except StoreError as exc:
            raise BackupError("store", str(exc)) from None
        except crypto.CryptoError as exc:
            raise BackupError("verify", str(exc)) from None
        run_tool("pg_restore", conn, ["--list"], code="verify", env=env, stdin=plain, stdout=tmp / "toc.txt")
    return manifest


# --- retention and freshness ------------------------------------------------------------------------------------------

def list_backups(store: ObjectStore, prefix: str) -> list[tuple[datetime, str]]:
    """Complete backups only: the manifest is written last, so an object without one is an unfinished upload."""
    found = []
    for key in store.list(f"{prefix}/"):
        match = STEM_RE.match(key)
        if match and match["prefix"] == prefix:
            found.append((datetime.strptime(match["ts"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), key.removesuffix(".manifest.json")))
    return sorted(found, reverse=True)


def select_keep(stamps: list[datetime], daily: int, weekly: int) -> set[datetime]:
    """Newest backup of each of the `daily` most recent days and `weekly` most recent ISO weeks that have one."""
    keep, days, weeks = set(), {}, {}
    for stamp in sorted(stamps, reverse=True):
        days.setdefault(stamp.date(), stamp)
        weeks.setdefault(stamp.isocalendar()[:2], stamp)
    keep.update(list(days.values())[:daily])
    keep.update(list(weeks.values())[:weekly])
    return keep


def prune(store: ObjectStore, prefix: str, daily: int, weekly: int) -> list[str]:
    if daily < 1 or weekly < 0:
        raise BackupError("config", "BACKUP_KEEP_DAILY must be at least 1 and BACKUP_KEEP_WEEKLY at least 0")
    backups = list_backups(store, prefix)
    keep = select_keep([b[0] for b in backups], daily, weekly)
    doomed = [stem for when, stem in backups if when not in keep]
    try:
        for stem in doomed:  # manifest first: a half-deleted backup then disappears instead of looking restorable
            store.delete(f"{stem}.manifest.json")
            store.delete(f"{stem}.pgdump.enc")
    except StoreError as exc:
        raise BackupError("retention", f"retention failed after the new backup succeeded: {exc}") from None
    return doomed


def check_freshness(store: ObjectStore, prefix: str, max_age_hours: float, now: datetime | None = None) -> datetime:
    """Dead-man's switch for the scheduler: fails when the newest complete backup in the store is too old or absent.
    It trusts the object name; `verify` is what proves the content."""
    now = now or datetime.now(timezone.utc)
    try:
        backups = list_backups(store, prefix)
    except StoreError as exc:
        raise BackupError("store", str(exc)) from None
    if not backups:
        raise BackupError("stale", "no complete backup exists in the destination")
    newest = backups[0][0]
    if now - newest > timedelta(hours=max_age_hours):
        raise BackupError("stale", f"newest backup is from {newest.isoformat()}, older than {max_age_hours:g}h")
    return newest


# --- restore drill ----------------------------------------------------------------------------------------------------

COUNT_SQL = """select table_name || '|' || (xpath('/row/c/text()', query_to_xml(
  format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE' order by 1"""


def drill_guard(target: PgConn, source: PgConn | None, confirm: str) -> None:
    """Fail closed unless the target is clearly a disposable, empty database on a different instance than the source."""
    if confirm != target.dbname:
        raise BackupError("config", "pass --confirm-disposable-target with the exact target database name")
    if not DRILL_DB_RE.match(target.dbname):
        raise BackupError("config", "drill target database name must match restore_drill_[a-z0-9_]+")
    if target.host not in LOOPBACK:
        raise BackupError("config", "drill target must be on this machine (localhost); remote hosts are refused")
    if source and (source.host, source.port or "5432") == (target.host, target.port or "5432"):
        raise BackupError("config", "drill target is the same PostgreSQL instance as the backup source; use a separate disposable instance")


def restore_drill(store: ObjectStore, stem: str, passphrase: str, target: PgConn, confirm: str, evidence_dir: Path, *,
                  source: PgConn | None = None, work_dir: str | None = None, env: Mapping[str, str] = os.environ) -> dict:
    """Restores one backup into an empty disposable database and writes an evidence file. Never touches the source."""
    drill_guard(target, source, confirm)
    started = datetime.now(timezone.utc)
    existing = psql(target, "select count(*) from pg_tables where schemaname not in ('pg_catalog', 'information_schema')", code="drill", env=env)
    if existing != [["0"]]:
        raise BackupError("drill", "drill target database is not empty; create a fresh restore_drill_* database")
    with private_dir(work_dir) as tmp:
        plain = tmp / "dump.pgdump"
        manifest = verify_backup(store, stem, passphrase, conn=target, work_dir=work_dir, env=env, decrypted_to=plain)
        run_tool("pg_restore", target, ["--exit-on-error", "--single-transaction", "--no-owner", "--no-acl",
                                        f"--dbname={target.dbname}"], code="drill", env=env, stdin=plain)
    counts = {name: int(n) for name, n in psql(target, COUNT_SQL, code="drill", env=env)}
    snapshot = schema_snapshot(target, env)
    missing = sorted(set(manifest["tables"]) - set(snapshot["tables"]))
    problems = [f"missing tables: {', '.join(missing)}"] if missing else []
    if snapshot["alembic_version"] != manifest["alembic_version"]:
        problems.append(f"alembic_version {snapshot['alembic_version']!r} != recorded {manifest['alembic_version']!r}")
    evidence = {"result": "failed" if problems else "passed", "problems": problems, "backup": stem,
                "created_at": manifest["created_at"], "ciphertext_sha256": manifest["ciphertext_sha256"],
                "mac_verified": True, "restored_database": target.dbname, "tables": counts,
                "alembic_version": snapshot["alembic_version"], "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat()}
    evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = evidence_dir / f"drill-{started:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True))
    path.chmod(0o600)
    if problems:
        raise BackupError("drill", f"restore drill failed (evidence: {path}): " + "; ".join(problems))
    return {**evidence, "evidence_file": str(path)}
