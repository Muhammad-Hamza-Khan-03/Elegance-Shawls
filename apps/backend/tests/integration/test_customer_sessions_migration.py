"""Migration 0015 (customer sessions): additive, immediately after 0014, reversible, and it never touches the tables it references."""
import hashlib
import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.exc import DBAPIError

from tests.integration.api_support import ApiEnv
from tests.integration.conftest import alembic_config

HASH = hashlib.sha256(b"cs1.x").hexdigest()


def tables(env):
    return {r[0] for r in env.sql("select table_name from information_schema.tables where table_schema = 'public'")}


@pytest.fixture
def at_0014(pg_url, migrated_url, pg_engine_factory, monkeypatch):
    config = alembic_config(pg_url)
    command.downgrade(config, "0014")
    yield config, ApiEnv(pg_url, monkeypatch)
    monkeypatch.undo()
    command.upgrade(config, "head")


def test_revision_chain_follows_0014(pg_url):
    script = ScriptDirectory.from_config(alembic_config(pg_url))
    rev = script.get_revision("0015")
    assert rev.down_revision == "0014" and script.get_revision("0014").nextrev == {"0015"}
    assert script.get_heads() == ["0015"]


def test_upgrade_adds_only_the_sessions_table_and_keeps_existing_rows(at_0014):
    config, env = at_0014
    cid = env.sql("insert into customers (status) values ('registered') returning id")[0][0]
    env.sql("insert into customer_identities (customer_id, provider, subject) values (:c, 'google', 'sub-1')", c=cid)
    before = tables(env)
    command.upgrade(config, "0015")
    assert tables(env) - before == {"customer_sessions"}
    assert env.sql("select count(*) from customers")[0][0] == 1 and env.sql("select count(*) from customer_identities")[0][0] == 1
    assert env.sql("select count(*) from customer_sessions")[0][0] == 0


def test_downgrade_drops_the_table_even_with_sessions_and_keeps_customers(at_0014):
    config, env = at_0014
    command.upgrade(config, "0015")
    cid = env.sql("insert into customers (status) values ('registered') returning id")[0][0]
    env.sql("insert into customer_sessions (customer_id, token_hash, expires_at) values (:c, :h, now() + interval '1 hour')", c=cid, h=HASH)
    command.downgrade(config, "0014")
    assert "customer_sessions" not in tables(env)
    assert env.sql("select count(*) from customers")[0][0] == 1
    command.upgrade(config, "0015")                                     # and it comes back, empty
    assert env.sql("select count(*) from customer_sessions")[0][0] == 0


def test_no_row_level_security_on_the_new_table(at_0014):
    config, env = at_0014
    command.upgrade(config, "0015")
    assert env.sql("select relrowsecurity from pg_class where relname = 'customer_sessions'") == [(False,)]


def test_constraints(at_0014):
    config, env = at_0014
    command.upgrade(config, "0015")
    cid = env.sql("insert into customers (status) values ('registered') returning id")[0][0]
    insert = "insert into customer_sessions (customer_id, token_hash, expires_at) values (:c, :h, now() + interval '1 hour')"
    env.sql(insert, c=cid, h=HASH)
    for bad in (HASH, "short", HASH.upper(), "g" * 64):                  # duplicate, malformed
        with pytest.raises(DBAPIError):
            env.sql(insert, c=cid, h=bad)
    with pytest.raises(DBAPIError):
        env.sql("insert into customer_sessions (customer_id, token_hash, expires_at) values (:c, :h, now() - interval '1 hour')",
                c=cid, h=hashlib.sha256(b"y").hexdigest())
    with pytest.raises(DBAPIError):
        env.sql(insert, c=uuid.uuid4(), h=hashlib.sha256(b"z").hexdigest())          # unknown customer
    env.sql("delete from customers where id = :c", c=cid)                              # cascade
    assert env.sql("select count(*) from customer_sessions")[0][0] == 0
