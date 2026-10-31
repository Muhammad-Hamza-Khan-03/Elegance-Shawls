"""Migration 0010 safety: additive on upgrade, and a downgrade that refuses to destroy admin data silently."""
import pytest
from alembic import command
from sqlalchemy import text

from tests.integration.api_support import ApiEnv
from tests.integration.conftest import alembic_config

LEGACY_AUDIT = "insert into audit_log (actor_type, actor_id, action, target) values ('admin', 'old-actor', 'old.action', 'product:1')"
ACCOUNT = ("insert into admin_accounts (email, role, password_hash) values ('o@example.com', 'owner', 'scrypt$x')")


def tables(env):
    return {r[0] for r in env.sql("select table_name from information_schema.tables where table_schema = 'public'")}


@pytest.fixture
def at_0009(pg_url, migrated_url, pg_engine_factory, monkeypatch):
    """Database stepped back to 0006 (empty), restored to head afterwards because later tests share it."""
    config = alembic_config(pg_url)
    command.downgrade(config, "0009")
    yield config, ApiEnv(pg_url, monkeypatch)
    monkeypatch.undo()
    command.upgrade(config, "head")


def test_upgrade_keeps_existing_audit_rows_and_defaults_them_to_success(at_0009):
    config, env = at_0009
    env.sql(LEGACY_AUDIT)
    command.upgrade(config, "0010")
    assert env.sql("select actor_id, action, target, outcome, detail from audit_log") == [("old-actor", "old.action", "product:1", "success", None)]
    assert {"admin_accounts", "admin_sessions"} <= tables(env)
    assert env.sql("select count(*) from admin_accounts")[0][0] == 0                  # no seeded or default account


def test_downgrade_refuses_to_destroy_accounts_unless_explicitly_allowed(at_0009, monkeypatch):
    config, env = at_0009
    env.sql(LEGACY_AUDIT)
    command.upgrade(config, "0010")
    env.sql(ACCOUNT)

    monkeypatch.delenv("ALEMBIC_ALLOW_ADMIN_DATA_LOSS", raising=False)
    with pytest.raises(Exception, match="Refusing to downgrade 0010"):
        command.downgrade(config, "0009")
    assert "admin_accounts" in tables(env) and env.sql("select count(*) from admin_accounts")[0][0] == 1     # nothing was touched

    monkeypatch.setenv("ALEMBIC_ALLOW_ADMIN_DATA_LOSS", "1")
    command.downgrade(config, "0009")
    assert not {"admin_accounts", "admin_sessions"} & tables(env)
    assert env.sql("select actor_id, action from audit_log") == [("old-actor", "old.action")]               # attribution survives rollback
    assert not env.sql("select 1 from information_schema.columns where table_name = 'audit_log' and column_name in ('outcome', 'detail')")


def test_downgrade_also_refuses_when_only_audit_outcomes_would_be_lost(at_0009, monkeypatch):
    config, env = at_0009
    command.upgrade(config, "0010")
    env.sql("insert into audit_log (actor_type, action, outcome) values ('admin', 'POST /x', 'denied')")
    monkeypatch.delenv("ALEMBIC_ALLOW_ADMIN_DATA_LOSS", raising=False)
    with pytest.raises(Exception, match="Refusing to downgrade 0010"):
        command.downgrade(config, "0009")


def test_downgrade_of_an_untouched_0010_needs_no_override(at_0009, monkeypatch):
    config, env = at_0009
    command.upgrade(config, "0010")
    monkeypatch.delenv("ALEMBIC_ALLOW_ADMIN_DATA_LOSS", raising=False)
    command.downgrade(config, "0009")
    assert not {"admin_accounts", "admin_sessions"} & tables(env)
