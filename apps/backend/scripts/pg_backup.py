"""Operator CLI for encrypted PostgreSQL backups. Run from apps/backend. Nothing here schedules itself or contacts a provider.

  python scripts/pg_backup.py backup                  # dump, encrypt, verify, store, then retention
  python scripts/pg_backup.py verify [--stem S]       # authenticate + decrypt + pg_restore --list (default: newest)
  python scripts/pg_backup.py decrypt --output FILE [--stem S]   # verified plaintext pg_dump archive (0600, never overwrites)
  python scripts/pg_backup.py check-freshness         # exit 7 when the newest backup is missing or too old
  python scripts/pg_backup.py restore-drill --confirm-disposable-target restore_drill_x --evidence-dir DIR [--stem S]

Configuration is environment-only (see OPERATIONS.md): BACKUP_DATABASE_URL, BACKUP_ENCRYPTION_PASSPHRASE (each also as
NAME_FILE), BACKUP_STORE_DIR, BACKUP_PREFIX, BACKUP_KEEP_DAILY/WEEKLY, BACKUP_MAX_AGE_HOURS, BACKUP_WORK_DIR and, for the
drill, RESTORE_DRILL_DATABASE_URL. Failures print `ALERT elegance-backup <code>: <message>` to stderr and exit non-zero
(2 config, 3 dump, 4 verify, 5 store, 6 retention, 7 stale, 8 drill, 9 role); the message never contains secrets.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backup import runner  # noqa: E402
from backup.runner import BackupError, PgConn, read_secret  # noqa: E402
from backup.store import LocalDirStore, StoreError  # noqa: E402


def int_env(env, name: str, default: int) -> int:
    try:
        return int(env.get(name) or default)
    except ValueError:
        raise BackupError("config", f"{name} must be an integer") from None


def build_store(env):
    root = env.get("BACKUP_STORE_DIR")
    if not root:
        raise BackupError("config", "BACKUP_STORE_DIR is not set (no off-server adapter is implemented or activated; see OPERATIONS.md)")
    if env.get("BACKUP_S3_ENDPOINT"):
        raise BackupError("config", "BACKUP_S3_* is set but no S3-compatible adapter is implemented; refusing to ignore it")
    print("WARNING: BACKUP_STORE_DIR is a local directory, not an off-server copy; it does not protect against losing this host.", file=sys.stderr)
    return LocalDirStore(Path(root))


def run(args, env) -> dict:
    prefix = env.get("BACKUP_PREFIX", "postgres")
    store = build_store(env)
    if args.command == "check-freshness":
        try:
            hours = float(env.get("BACKUP_MAX_AGE_HOURS") or 26)
        except ValueError:
            raise BackupError("config", "BACKUP_MAX_AGE_HOURS must be a number") from None
        return {"status": "fresh", "newest": runner.check_freshness(store, prefix, hours).isoformat()}

    conn = PgConn.from_url(read_secret(env, "BACKUP_DATABASE_URL"), "BACKUP_DATABASE_URL")
    passphrase = read_secret(env, "BACKUP_ENCRYPTION_PASSPHRASE")
    work_dir = env.get("BACKUP_WORK_DIR") or None
    stem = getattr(args, "stem", None)
    if args.command != "backup" and not stem:
        backups = runner.list_backups(store, prefix)
        if not backups:
            raise BackupError("stale", "no complete backup exists in the destination")
        stem = backups[0][1]

    if args.command == "backup":
        result = runner.create_backup(conn, passphrase, store, prefix=prefix, keep_daily=int_env(env, "BACKUP_KEEP_DAILY", 14),
                                      keep_weekly=int_env(env, "BACKUP_KEEP_WEEKLY", 8), work_dir=work_dir, env=env)
        out = {"status": "ok", "stem": result.stem, "off_server": store.off_server, "pruned": result.pruned}
        if result.retention_error:
            out.update(status="retention_failed", error=result.retention_error)
        return out
    if args.command == "verify":
        manifest = runner.verify_backup(store, stem, passphrase, conn=conn, work_dir=work_dir, env=env)
        return {"status": "verified", "stem": stem, "created_at": manifest["created_at"], "ciphertext_sha256": manifest["ciphertext_sha256"]}
    if args.command == "decrypt":
        out = Path(args.output)
        os.close(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))  # owner-only before any plaintext is written
        try:
            manifest = runner.verify_backup(store, stem, passphrase, conn=conn, work_dir=work_dir, env=env, decrypted_to=out)
        except BaseException:
            out.unlink(missing_ok=True)
            raise
        return {"status": "decrypted", "stem": stem, "output": str(out), "plaintext_sha256": manifest["plaintext_sha256"]}
    target = PgConn.from_url(read_secret(env, "RESTORE_DRILL_DATABASE_URL"), "RESTORE_DRILL_DATABASE_URL")
    return runner.restore_drill(store, stem, passphrase, target, args.confirm_disposable_target, Path(args.evidence_dir),
                                source=conn, work_dir=work_dir, env=env)


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup")
    sub.add_parser("check-freshness")
    for name in ("verify", "decrypt", "restore-drill"):
        p = sub.add_parser(name)
        p.add_argument("--stem")
    sub.choices["decrypt"].add_argument("--output", required=True)
    drill = sub.choices["restore-drill"]
    drill.add_argument("--confirm-disposable-target", required=True)
    drill.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args, env)
    except (BackupError, StoreError) as exc:
        code = exc.code if isinstance(exc, BackupError) else "store"
        print(f"ALERT elegance-backup {code}: {exc}", file=sys.stderr)
        return runner.EXIT_CODES[code]
    except Exception as exc:  # fail closed without echoing anything that could carry a secret
        print(f"ALERT elegance-backup internal: unexpected {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    if result.get("status") == "retention_failed":
        print(f"ALERT elegance-backup retention: {result['error']}", file=sys.stderr)
        return runner.EXIT_CODES["retention"]
    return 0


if __name__ == "__main__":
    sys.exit(main())
