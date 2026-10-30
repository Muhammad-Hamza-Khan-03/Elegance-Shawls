"""Backup -> encrypt -> verify -> restore drill against real, disposable PostgreSQL containers (Testcontainers).

The source is the shared integration database (roles from deploy/postgres/init-roles.sh); the drill target is a second,
separate container. The real PostgreSQL client tools run inside those containers through deploy/postgres/container-pg.sh.
Nothing here can reach a shared or production database: every URL points at a container created by this module's fixtures.
"""
import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from backup import runner
from backup.runner import BackupError, PgConn
from backup.store import LocalDirStore
from tests.integration.conftest import APP_PASSWORD, APP_USER, PG_IMAGE

WRAPPER = Path(__file__).resolve().parents[4] / "deploy/postgres/container-pg.sh"
PASS = "integration-test-passphrase-0123456789abcdef"
BACKUP_PASSWORD = "backup-role-test-password"


@pytest.fixture(scope="module")
def drill_container(docker_client):
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(PG_IMAGE, username="drill_admin", password="drill-test-password", dbname="restore_drill_it") as container:
        yield container


def tool_env(container) -> dict:
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "POSTGRES_CONTAINER": container.get_wrapped_container().id,
            "PG_DUMP_CMD": f"{WRAPPER} pg_dump", "PG_RESTORE_CMD": f"{WRAPPER} pg_restore", "PSQL_CMD": f"{WRAPPER} psql"}


def conn_for(container, user: str, password: str, dbname: str) -> PgConn:
    return PgConn(container.get_container_host_ip(), str(container.get_exposed_port(5432)), user, password, dbname)


@pytest.fixture
def source(pg_container, pg_engine_factory):
    """The migrated source database holding three customers, plus the env that reaches its container."""
    async def seed():
        engine = pg_engine_factory()
        async with engine.begin() as sql:
            for _ in range(3):
                await sql.execute(text("insert into customers default values"))
        await engine.dispose()

    asyncio.run(seed())
    return pg_container, tool_env(pg_container)


def test_backup_role_contract_holds_for_the_real_roles(source):
    container, env = source
    inspect = lambda user, password: runner.role_violations(runner.psql(conn_for(container, user, password, "elegance_test"), runner.ROLE_SQL, code="role", env=env)[0])
    assert inspect("backup_role", BACKUP_PASSWORD) == []
    assert any("write to" in v or "CREATE" in v for v in inspect(APP_USER, APP_PASSWORD))
    assert any("superuser" in v for v in inspect("admin_role", "admin-role-test-password"))


def test_backup_refuses_the_application_role(source, tmp_path):
    container, env = source
    store = LocalDirStore(tmp_path / "store")
    with pytest.raises(BackupError) as err:
        runner.create_backup(conn_for(container, APP_USER, APP_PASSWORD, "elegance_test"), PASS, store, work_dir=str(tmp_path), env=env)
    assert err.value.code == "role" and APP_PASSWORD not in str(err.value) and store.list() == []


def test_encrypted_backup_restores_into_a_disposable_instance_with_evidence(source, drill_container, tmp_path):
    container, env = source
    store = LocalDirStore(tmp_path / "store")
    src = conn_for(container, "backup_role", BACKUP_PASSWORD, "elegance_test")

    result = runner.create_backup(src, PASS, store, work_dir=str(tmp_path), env=env)
    assert result.retention_error is None and result.manifest["alembic_version"] and "customers" in result.manifest["tables"]
    blob = (tmp_path / "store" / f"{result.stem}.pgdump.enc").read_bytes()
    assert b"PGDMP" not in blob and b"customers" not in blob  # nothing readable at rest

    target = conn_for(drill_container, "drill_admin", "drill-test-password", "restore_drill_it")
    drill_env = tool_env(drill_container)
    evidence = runner.restore_drill(store, result.stem, PASS, target, "restore_drill_it", tmp_path / "evidence", source=src, work_dir=str(tmp_path), env=drill_env)

    source_counts = {name: int(n) for name, n in runner.psql(src, runner.COUNT_SQL, code="drill", env=env)}
    assert evidence["result"] == "passed" and evidence["tables"] == source_counts and source_counts["customers"] == 3
    assert evidence["alembic_version"] == result.manifest["alembic_version"]
    assert json.loads(Path(evidence["evidence_file"]).read_text())["ciphertext_sha256"] == result.manifest["ciphertext_sha256"]

    with pytest.raises(BackupError, match="not empty"):  # a drill target is single-use
        runner.restore_drill(store, result.stem, PASS, target, "restore_drill_it", tmp_path / "evidence", source=src, work_dir=str(tmp_path), env=drill_env)

    blob_path = tmp_path / "store" / f"{result.stem}.pgdump.enc"
    raw = bytearray(blob_path.read_bytes()); raw[500] ^= 1; blob_path.write_bytes(bytes(raw))
    with pytest.raises(BackupError, match="corrupt"):
        runner.verify_backup(store, result.stem, PASS, conn=src, work_dir=str(tmp_path), env=env)
