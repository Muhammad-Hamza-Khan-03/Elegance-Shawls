"""Container-free tests for the backup foundation: crypto, destination contract, retention, failure semantics, role contract,
restore-drill safety. PostgreSQL tools are replaced by a fake script; nothing touches a database or the network."""
import json
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backup import crypto, runner
from backup.runner import BackupError, PgConn
from backup.store import LocalDirStore, S3Settings, StoreError

REPO = Path(__file__).resolve().parents[3]
PASS = "correct horse battery staple, generated 0123456789abcdef"
DB_PASSWORD = "s3cr3t-db-password"
SOURCE_URL = f"postgresql://elegance_backup:{DB_PASSWORD}@127.0.0.1:5432/elegance_shawls"
TARGET_URL = f"postgresql://postgres:{DB_PASSWORD}@127.0.0.1:5433/restore_drill_a1"
NOW = datetime(2026, 11, 3, 3, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is required")

FAKE = '''#!{python}
import json, os, sys
tool, argv = sys.argv[1], sys.argv[2:]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({{"tool": tool, "argv": argv, "pgpassword": os.environ.get("PGPASSWORD"),
                          "env_keys": sorted(os.environ)}}) + "\\n")
if os.environ.get("FAKE_FAIL") == tool:
    sys.stderr.write("connection failed: postgresql://u:" + os.environ["PGPASSWORD"] + "@h/db password=" + os.environ["PGPASSWORD"])
    sys.exit(1)
if tool == "pg_dump":
    print("pg_dump (PostgreSQL) 17.0") if argv == ["--version"] else sys.stdout.buffer.write(b"PGDMP" + os.urandom(4096))
elif tool == "pg_restore":
    data = sys.stdin.buffer.read()
    if not data.startswith(b"PGDMP"):
        sys.stderr.write("not a valid archive"); sys.exit(1)
    if "--list" in argv: print("; TOC")
elif tool == "psql":
    sql = argv[argv.index("-c") + 1]
    if "rolsuper" in sql: print(os.environ.get("FAKE_ROLE", "f|f|f|f|f|f|f|t|f|0"))
    elif "not in" in sql: print(os.environ.get("FAKE_EXISTING", "0"))
    elif "query_to_xml" in sql: print(os.environ.get("FAKE_COUNTS", "alembic_version|1\\nproducts|3\\nvariants|5"))
    elif "version_num" in sql: print(os.environ.get("FAKE_ALEMBIC", "0008"))
    else: print(os.environ.get("FAKE_TABLES", "alembic_version\\nproducts\\nvariants"))
'''


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(crypto, "KDF_ITER", crypto.MIN_KDF_ITER)


@pytest.fixture
def env(tmp_path):
    fake = tmp_path / "fake_pg.py"
    fake.write_text(FAKE.format(python=sys.executable))
    fake.chmod(0o700)
    return {"PATH": "/usr/bin:/bin", "FAKE_LOG": str(tmp_path / "calls.log"), "BACKUP_ENCRYPTION_PASSPHRASE": PASS,
            "PG_DUMP_CMD": f"{fake} pg_dump", "PG_RESTORE_CMD": f"{fake} pg_restore", "PSQL_CMD": f"{fake} psql"}


@pytest.fixture
def conn():
    return PgConn.from_url(SOURCE_URL, "BACKUP_DATABASE_URL")


@pytest.fixture
def store(tmp_path):
    return LocalDirStore(tmp_path / "store")


def calls(env):
    return [json.loads(line) for line in Path(env["FAKE_LOG"]).read_text().splitlines()]


def backup(conn, store, env, tmp_path, now=NOW, **kw):
    return runner.create_backup(conn, PASS, store, work_dir=str(tmp_path), env=env, now=now, **kw)


# --- crypto -----------------------------------------------------------------------------------------------------------

def encrypted(tmp_path, data=b"PGDMP" + b"x" * 5000):
    plain, cipher = tmp_path / "p", tmp_path / "c"
    plain.write_bytes(data)
    return plain, cipher, crypto.encrypt_file(plain, cipher, PASS, {"database": "d"})


def test_roundtrip_and_ciphertext_hides_plaintext(tmp_path):
    plain, cipher, manifest = encrypted(tmp_path)
    assert b"xxxxxxxx" not in cipher.read_bytes()
    out = tmp_path / "out"
    crypto.decrypt_file(cipher, out, PASS, manifest)
    assert out.read_bytes() == plain.read_bytes()


def test_default_kdf_cost_is_recorded(tmp_path, monkeypatch):
    monkeypatch.undo()
    assert encrypted(tmp_path)[2]["kdf_iter"] == 600_000


def test_wrong_passphrase_rejected_before_decrypting(tmp_path):
    _, cipher, manifest = encrypted(tmp_path)
    with pytest.raises(crypto.CryptoError, match="authentication failed"):
        crypto.decrypt_file(cipher, tmp_path / "out", PASS + "x", manifest)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("tamper", ["cipher_flip", "truncate", "manifest_digest", "manifest_field", "kdf_downgrade", "kdf_dos", "no_mac"])
def test_tampering_is_detected(tmp_path, tamper):
    _, cipher, manifest = encrypted(tmp_path)
    if tamper == "cipher_flip":
        raw = bytearray(cipher.read_bytes()); raw[100] ^= 1; cipher.write_bytes(bytes(raw))
    elif tamper == "truncate":
        cipher.write_bytes(cipher.read_bytes()[:-16])
    elif tamper == "manifest_digest":
        manifest["plaintext_sha256"] = "0" * 64
    elif tamper == "manifest_field":
        manifest["database"] = "other"
    elif tamper == "kdf_downgrade":
        manifest["kdf_iter"] = 1
    elif tamper == "kdf_dos":
        manifest["kdf_iter"] = 10**12
    else:
        del manifest["mac"]
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_file(cipher, tmp_path / "out", PASS, manifest)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("bad", ["", "short", "replace-with-openssl-rand-hex-32-padding-padding"])
def test_weak_or_placeholder_passphrase_refused(tmp_path, bad):
    plain = tmp_path / "p"; plain.write_bytes(b"data")
    with pytest.raises(crypto.CryptoError):
        crypto.encrypt_file(plain, tmp_path / "c", bad, {})


def test_passphrase_never_reaches_argv(tmp_path, monkeypatch):
    seen = []
    real = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or real(cmd, **kw))
    encrypted(tmp_path)
    assert seen and all(PASS not in " ".join(cmd) for cmd in seen)


# --- destination contract ---------------------------------------------------------------------------------------------

def test_store_contract(tmp_path, store):
    src = tmp_path / "src"; src.write_bytes(b"hello")
    store.put("postgres/a.enc", src)
    store.put("postgres/b.enc", src)
    store.put("other/c.enc", src)
    assert store.list("postgres/") == ["postgres/a.enc", "postgres/b.enc"]
    with pytest.raises(StoreError, match="already exists"):
        store.put("postgres/a.enc", src)  # immutable
    dest = tmp_path / "dest"; store.get("postgres/a.enc", dest)
    assert dest.read_bytes() == b"hello"
    with pytest.raises(StoreError):
        store.get("postgres/missing", tmp_path / "x")
    store.delete("postgres/a.enc"); store.delete("postgres/a.enc")  # idempotent
    assert store.list("postgres/") == ["postgres/b.enc"]
    assert not [p for p in (tmp_path / "store").rglob(".partial-*")]


@pytest.mark.parametrize("key", ["../x", "/abs", "a/../b", "a//b", "", "a b", "a/.hidden", "x\n"])
def test_store_rejects_unsafe_keys(store, tmp_path, key):
    (tmp_path / "s").write_bytes(b"x")
    with pytest.raises(StoreError):
        store.put(key, tmp_path / "s")


def test_local_store_declares_it_is_not_off_server(store):
    assert store.off_server is False


S3_ENV = {"BACKUP_S3_ENDPOINT": "https://s3.example.invalid", "BACKUP_S3_BUCKET": "es-backups", "BACKUP_S3_ACCESS_KEY_ID": "AKIDEXAMPLE",
          "BACKUP_S3_SECRET_ACCESS_KEY": "super-secret-key"}


def test_s3_settings_valid_and_secrets_not_in_repr():
    settings = S3Settings.from_env(S3_ENV)
    assert (settings.bucket, settings.prefix, settings.region) == ("es-backups", "postgres", "auto")
    assert "super-secret-key" not in repr(settings) and "AKIDEXAMPLE" not in repr(settings)


@pytest.mark.parametrize("change", [
    {"BACKUP_S3_ENDPOINT": "http://s3.example.invalid"}, {"BACKUP_S3_ENDPOINT": "https://u:p@s3.example.invalid"},
    {"BACKUP_S3_ENDPOINT": "https://s3.example.invalid/?x=1"}, {"BACKUP_S3_BUCKET": "Bad_Bucket"},
    {"BACKUP_S3_SECRET_ACCESS_KEY": ""}, {"BACKUP_S3_ACCESS_KEY_ID": "replace-with-key"}, {"BACKUP_S3_PREFIX": "../x"}])
def test_s3_settings_fail_closed(change):
    with pytest.raises(StoreError) as err:
        S3Settings.from_env({**S3_ENV, **change})
    assert "super-secret-key" not in str(err.value)


# --- retention --------------------------------------------------------------------------------------------------------

def test_select_keep_daily_then_weekly():
    stamps = [NOW - timedelta(days=d, hours=h) for d in range(60) for h in (0, 1)]  # two per day
    keep = runner.select_keep(stamps, daily=14, weekly=8)
    days = {s.date() for s in keep}
    assert all((NOW - timedelta(days=d)).date() in days for d in range(14))
    assert len(keep) <= 14 + 8 and NOW in keep
    assert NOW - timedelta(hours=1) not in keep  # only the newest per day


def test_select_keep_with_gaps_never_ages_out_the_last_copies():
    stamps = [NOW - timedelta(days=100), NOW - timedelta(days=99)]
    assert runner.select_keep(stamps, 1, 0) == {NOW - timedelta(days=99)}


def test_backup_applies_retention_after_success(conn, store, env, tmp_path):
    for d in range(1, 5):
        backup(conn, store, env, tmp_path, now=NOW - timedelta(days=d))
    result = backup(conn, store, env, tmp_path, keep_daily=2, keep_weekly=0)
    assert len(runner.list_backups(store, "postgres")) == 2
    assert len(result.pruned) == 3
    assert not [k for k in store.list() if "20261030" in k]  # data objects went with their manifests


def test_retention_failure_is_reported_but_backup_survives(conn, store, env, tmp_path, monkeypatch):
    backup(conn, store, env, tmp_path, now=NOW - timedelta(days=3))
    monkeypatch.setattr(store, "delete", lambda key: (_ for _ in ()).throw(StoreError("disk error")))
    result = backup(conn, store, env, tmp_path, keep_daily=1, keep_weekly=0)
    assert "retention failed" in result.retention_error
    assert len(runner.list_backups(store, "postgres")) == 2  # nothing lost


def test_retention_does_not_run_when_the_backup_fails(conn, store, env, tmp_path):
    backup(conn, store, env, tmp_path, now=NOW - timedelta(days=3))
    env["FAKE_FAIL"] = "pg_dump"
    with pytest.raises(BackupError):
        backup(conn, store, env, tmp_path, keep_daily=1, keep_weekly=0)
    assert len(runner.list_backups(store, "postgres")) == 1


def test_prune_refuses_nonsense_policy(store):
    with pytest.raises(BackupError, match="at least 1"):
        runner.prune(store, "postgres", 0, 8)


# --- backup flow and failure semantics ---------------------------------------------------------------------------------

def test_backup_happy_path(conn, store, env, tmp_path):
    result = backup(conn, store, env, tmp_path)
    assert result.stem == "postgres/elegance-20261103T030000Z"
    assert store.list() == [f"{result.stem}.manifest.json", f"{result.stem}.pgdump.enc"]
    manifest = json.loads((tmp_path / "store" / f"{result.stem}.manifest.json").read_text())
    assert manifest["tables"] == ["alembic_version", "products", "variants"] and manifest["alembic_version"] == "0008"
    assert PASS not in json.dumps(manifest) and DB_PASSWORD not in json.dumps(manifest)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("es-backup-")]  # plaintext workspace removed
    assert runner.verify_backup(store, result.stem, PASS, conn=conn, work_dir=str(tmp_path), env=env)["database"] == "elegance_shawls"


def test_secrets_stay_out_of_argv_and_the_environment_of_children(conn, store, env, tmp_path):
    backup(conn, store, env, tmp_path)
    for call in calls(env):
        assert DB_PASSWORD not in " ".join(call["argv"]) and PASS not in " ".join(call["argv"])
        assert not any(k.startswith("BACKUP_") for k in call["env_keys"])  # the passphrase is not inherited
    assert {c["pgpassword"] for c in calls(env)} == {DB_PASSWORD}
    assert any("--no-password" in c["argv"] for c in calls(env) if c["tool"] == "pg_dump")


def test_dump_failure_is_redacted_and_uploads_nothing(conn, store, env, tmp_path):
    env["FAKE_FAIL"] = "pg_dump"
    with pytest.raises(BackupError) as err:
        backup(conn, store, env, tmp_path)
    assert err.value.code == "dump" and DB_PASSWORD not in str(err.value) and "***" in str(err.value)
    assert store.list() == []


def test_unusable_archive_is_refused(conn, store, env, tmp_path):
    env["FAKE_FAIL"] = "pg_restore"
    with pytest.raises(BackupError) as err:
        backup(conn, store, env, tmp_path)
    assert err.value.code == "dump" and store.list() == []


def test_failed_manifest_upload_removes_the_orphan_archive(conn, store, env, tmp_path, monkeypatch):
    real = store.put
    monkeypatch.setattr(store, "put", lambda key, src: (_ for _ in ()).throw(StoreError("quota exceeded")) if key.endswith(".json") else real(key, src))
    with pytest.raises(BackupError) as err:
        backup(conn, store, env, tmp_path)
    assert err.value.code == "store" and store.list() == []


def test_missing_tool_is_a_config_error(conn, store, env, tmp_path):
    env["PSQL_CMD"] = "/nonexistent/psql"
    with pytest.raises(BackupError) as err:
        backup(conn, store, env, tmp_path)
    assert err.value.code == "config"


def test_verify_detects_corruption_in_the_store(conn, store, env, tmp_path):
    stem = backup(conn, store, env, tmp_path).stem
    blob = tmp_path / "store" / f"{stem}.pgdump.enc"
    raw = bytearray(blob.read_bytes()); raw[200] ^= 1; blob.write_bytes(bytes(raw))
    with pytest.raises(BackupError) as err:
        runner.verify_backup(store, stem, PASS, conn=conn, work_dir=str(tmp_path), env=env)
    assert err.value.code == "verify" and "corrupt" in str(err.value)
    with pytest.raises(BackupError, match="wrong passphrase"):
        runner.verify_backup(store, stem, PASS + "x", conn=conn, work_dir=str(tmp_path), env=env)


@pytest.mark.parametrize("age_hours, ok", [(1, True), (25, True), (27, False)])
def test_freshness(conn, store, env, tmp_path, age_hours, ok):
    backup(conn, store, env, tmp_path, now=NOW)
    check = lambda: runner.check_freshness(store, "postgres", 26, now=NOW + timedelta(hours=age_hours))
    if ok:
        assert check() == NOW
    else:
        with pytest.raises(BackupError) as err:
            check()
        assert err.value.code == "stale"


def test_freshness_with_no_backups_alerts(store):
    with pytest.raises(BackupError, match="no complete backup"):
        runner.check_freshness(store, "postgres", 26)


def test_unfinished_upload_is_not_a_backup(store, tmp_path):
    (tmp_path / "s").write_bytes(b"x")
    store.put("postgres/elegance-20261103T030000Z.pgdump.enc", tmp_path / "s")  # data without manifest
    assert runner.list_backups(store, "postgres") == []


# --- least-privilege role contract ------------------------------------------------------------------------------------

GOOD_ROLE = "f|f|f|f|f|f|f|t|f|0".split("|")


def test_role_contract_accepts_only_the_read_only_role():
    assert runner.role_violations(GOOD_ROLE) == []
    for index, label in enumerate(runner.ROLE_MUST_BE_FALSE):
        bad = list(GOOD_ROLE); bad[index] = "t"
        assert label in " ".join(runner.role_violations(bad))
    assert "pg_read_all_data" in " ".join(runner.role_violations(["f"] * 7 + ["f", "f", "0"]))
    assert "pg_write_all_data" in " ".join(runner.role_violations(GOOD_ROLE[:8] + ["t", "0"]))
    assert "3 public table" in " ".join(runner.role_violations(GOOD_ROLE[:9] + ["3"]))
    assert runner.role_violations([]) == ["role could not be inspected"]


def test_backup_refuses_an_over_privileged_role_before_dumping(conn, store, env, tmp_path):
    env["FAKE_ROLE"] = "t|t|t|f|f|t|t|t|t|12"
    with pytest.raises(BackupError) as err:
        backup(conn, store, env, tmp_path)
    assert err.value.code == "role" and "superuser" in str(err.value)
    assert [c["tool"] for c in calls(env)] == ["psql"] and store.list() == []


def test_init_script_defines_the_documented_backup_role():
    sql = (REPO / "deploy/postgres/init-roles.sh").read_text()
    role = re.search(r'CREATE ROLE :"backup_user".*?;', sql, re.S)[0]
    assert all(attr in role for attr in ("NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE", "NOREPLICATION"))
    assert 'GRANT pg_read_all_data TO :"backup_user"' in sql
    lines = [line for line in sql.splitlines() if "backup_user" in line and line.startswith("GRANT")]
    assert not any(re.search(r"\b(CREATE|INSERT|UPDATE|DELETE|ALL)\b", line.replace("GRANT CONNECT", "")) for line in lines)


# --- restore drill safety ---------------------------------------------------------------------------------------------

def drill(store, env, tmp_path, stem, url=TARGET_URL, confirm=None, source=SOURCE_URL):
    target = PgConn.from_url(url, "RESTORE_DRILL_DATABASE_URL")
    return runner.restore_drill(store, stem, PASS, target, confirm or target.dbname, tmp_path / "evidence",
                                source=PgConn.from_url(source, "x"), work_dir=str(tmp_path), env=env)


@pytest.fixture
def stem(conn, store, env, tmp_path):
    return backup(conn, store, env, tmp_path).stem


@pytest.mark.parametrize("url, confirm, message", [
    (TARGET_URL, "wrong", "exact target database name"),
    (TARGET_URL.replace("restore_drill_a1", "elegance_shawls"), None, "restore_drill_"),
    (TARGET_URL.replace("restore_drill_a1", "restore_drill_A;drop"), None, "restore_drill_"),
    (TARGET_URL.replace("127.0.0.1", "db.example.com"), None, "localhost"),
    (TARGET_URL.replace(":5433", ":5432"), None, "same PostgreSQL instance"),
])
def test_drill_refuses_unsafe_targets_without_restoring(store, env, tmp_path, stem, url, confirm, message):
    with pytest.raises(BackupError, match=message) as err:
        drill(store, env, tmp_path, stem, url, confirm)
    assert err.value.code == "config"
    assert "pg_restore" not in [c["tool"] for c in calls(env) if "--dbname=restore_drill_a1" in c["argv"]]
    assert "--exit-on-error" not in " ".join(sum((c["argv"] for c in calls(env)), []))


def test_drill_refuses_a_non_empty_target(store, env, tmp_path, stem):
    env["FAKE_EXISTING"] = "7"
    with pytest.raises(BackupError, match="not empty"):
        drill(store, env, tmp_path, stem)
    assert "--exit-on-error" not in " ".join(sum((c["argv"] for c in calls(env)), []))


def test_drill_writes_evidence_on_success(store, env, tmp_path, stem):
    result = drill(store, env, tmp_path, stem)
    evidence = json.loads(Path(result["evidence_file"]).read_text())
    assert evidence["result"] == "passed" and evidence["mac_verified"] and evidence["restored_database"] == "restore_drill_a1"
    assert evidence["tables"] == {"alembic_version": 1, "products": 3, "variants": 5} and evidence["alembic_version"] == "0008"
    assert DB_PASSWORD not in json.dumps(evidence) and PASS not in json.dumps(evidence)
    assert stat.S_IMODE(Path(result["evidence_file"]).stat().st_mode) == 0o600
    restore = [c for c in calls(env) if "--exit-on-error" in c["argv"]][0]
    assert {"--no-owner", "--no-acl", "--single-transaction", "--dbname=restore_drill_a1"} <= set(restore["argv"])


@pytest.mark.parametrize("fake, message", [({"FAKE_TABLES": "alembic_version\nproducts"}, "missing tables: variants"),
                                           ({"FAKE_ALEMBIC": "0007"}, "alembic_version")])
def test_drill_fails_and_records_evidence_when_the_restore_is_incomplete(store, env, tmp_path, stem, fake, message):
    # the fake answers schema queries the same way for source and target, so only change them for the post-restore check
    Path(env["FAKE_LOG"]).write_text("")
    first = drill(store, env, tmp_path, stem)  # baseline passes
    assert first["result"] == "passed"
    env.update(fake)
    with pytest.raises(BackupError, match=message) as err:
        drill(store, env, tmp_path, stem)
    assert err.value.code == "drill"


# --- CLI ----------------------------------------------------------------------------------------------------------------

@pytest.fixture
def cli(env, tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("pg_backup_cli", Path(__file__).resolve().parents[1] / "scripts/pg_backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env.update(BACKUP_DATABASE_URL=SOURCE_URL, BACKUP_STORE_DIR=str(tmp_path / "cli-store"), BACKUP_WORK_DIR=str(tmp_path))
    return lambda *argv, **extra: module.main(list(argv), {**env, **extra})


def test_cli_backup_verify_freshness_and_alert_exit_codes(cli, env, capsys):
    assert cli("backup") == 0
    out, err = capsys.readouterr()
    assert json.loads(out)["off_server"] is False and "not an off-server copy" in err
    assert cli("verify") == 0 and json.loads(capsys.readouterr().out)["status"] == "verified"
    assert cli("check-freshness") == 0
    env["FAKE_FAIL"] = "pg_dump"
    assert cli("backup") == 3
    err = capsys.readouterr().err
    assert "ALERT elegance-backup dump:" in err and DB_PASSWORD not in err and PASS not in err


def test_cli_decrypt_writes_a_verified_owner_only_archive_and_never_overwrites(cli, tmp_path, capsys):
    assert cli("backup") == 0
    out = tmp_path / "restore.pgdump"
    assert cli("decrypt", "--output", str(out)) == 0
    assert out.read_bytes().startswith(b"PGDMP") and stat.S_IMODE(out.stat().st_mode) == 0o600
    capsys.readouterr()
    assert cli("decrypt", "--output", str(out)) == 1  # exists: refused, file untouched
    assert out.read_bytes().startswith(b"PGDMP")
    bad = tmp_path / "bad.pgdump"
    assert cli("decrypt", "--output", str(bad), BACKUP_ENCRYPTION_PASSPHRASE=PASS + "x") == 4 and not bad.exists()
    assert "wrong passphrase" in capsys.readouterr().err


def test_cli_stale_and_empty_destination_exit_7(cli, capsys):
    assert cli("check-freshness") == 7
    assert "ALERT elegance-backup stale" in capsys.readouterr().err
    assert cli("backup") == 0
    assert cli("check-freshness", BACKUP_MAX_AGE_HOURS="0") == 7


@pytest.mark.parametrize("extra, message", [
    ({"BACKUP_DATABASE_URL": ""}, "BACKUP_DATABASE_URL"),
    ({"BACKUP_DATABASE_URL": "mysql://u:p@h/db"}, "must look like"),
    ({"BACKUP_ENCRYPTION_PASSPHRASE": "short"}, "passphrase"),
    ({"BACKUP_STORE_DIR": ""}, "BACKUP_STORE_DIR"),
    ({"BACKUP_S3_ENDPOINT": "https://s3.example.invalid"}, "no S3-compatible adapter is implemented"),
    ({"BACKUP_KEEP_DAILY": "many"}, "integer")])
def test_cli_configuration_errors_fail_closed_with_exit_2(cli, capsys, extra, message):
    assert cli("backup", **extra) == 2
    err = capsys.readouterr().err
    assert message in err and DB_PASSWORD not in err and "mysql://u:p" not in err.replace("must look like", "")


def test_cli_secret_files_must_be_owner_only(cli, tmp_path, capsys):
    secret = tmp_path / "passphrase"
    secret.write_text(PASS + "\n")
    secret.chmod(0o644)
    env_extra = {"BACKUP_ENCRYPTION_PASSPHRASE": "", "BACKUP_ENCRYPTION_PASSPHRASE_FILE": str(secret)}
    assert cli("backup", **env_extra) == 2 and "readable by group or others" in capsys.readouterr().err
    secret.chmod(0o600)
    assert cli("backup", **env_extra) == 0


def test_cli_drill_requires_the_typed_confirmation_and_never_runs_unconfirmed(cli, tmp_path, capsys):
    assert cli("backup") == 0
    capsys.readouterr()
    code = cli("restore-drill", "--confirm-disposable-target", "nope", "--evidence-dir", str(tmp_path / "ev"), RESTORE_DRILL_DATABASE_URL=TARGET_URL)
    assert code == 2 and "exact target database name" in capsys.readouterr().err
    assert cli("restore-drill", "--confirm-disposable-target", "restore_drill_a1", "--evidence-dir", str(tmp_path / "ev"),
               RESTORE_DRILL_DATABASE_URL=TARGET_URL) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "passed"


def test_wrapper_script_is_executable_and_keeps_secrets_out_of_argv():
    script = REPO / "deploy/postgres/container-pg.sh"
    assert script.stat().st_mode & stat.S_IXUSR
    text = script.read_text()
    assert "-e PGPASSWORD " in text and "PGPASSWORD=" not in text and "eval" not in text
