"""Disposable PostgreSQL route coverage for M4-S4 ownership, consent and current catalogue reads."""
from datetime import datetime, timedelta, timezone
import hashlib
import uuid

import pytest
from fastapi import Header

from configuration.config import settings
from memory.principal import CustomerPrincipal, current_principal
from routes.suggestion_routes import router
from tests.integration.api_support import ApiEnv


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)
    e.app.include_router(router)
    customer = uuid.uuid4()

    async def principal(x_test_customer: str = Header(...)) -> CustomerPrincipal:
        assert x_test_customer == str(customer)
        token = "test-session"
        return CustomerPrincipal(customer, "session", hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc) + timedelta(hours=1))

    e.app.dependency_overrides[current_principal] = principal
    monkeypatch.setattr(settings, "llm_production_chain", "selfhost/llama")
    monkeypatch.setattr(settings, "llm_provider_training_policies", "selfhost=self_hosted")
    monkeypatch.setattr(settings, "llm_free_tier_providers", "")
    e.sql("insert into customers (id, status) values (:id, 'registered')", id=customer)
    e.sql("insert into memory_consents (customer_id, granted, policy_version, changed_at) values (:id, true, '2026-10-30', now())", id=customer)
    e.sql("""insert into products (id, slug, name, category, status, cover_image_url, images, price, currency, revision)
              values (:id, 'blue-shawl', 'Blue Shawl', 'shawls', 'active', 'https://example.test/blue.jpg', '{}', 5000, 'PKR', 4)""", id=uuid.uuid4())
    product_id = e.sql("select id from products where slug = 'blue-shawl'")[0][0]
    e.sql("""insert into variants (product_id, position, name, color, size, image_url, price, currency, stock)
              values (:product, 0, 'Standard', 'Blue', 'Free Size', 'https://example.test/blue.jpg', 5000, 'PKR', 2)""", product=product_id)
    memory_id = uuid.uuid4()
    e.sql("""insert into memory_items (id, customer_id, idempotency_key, category, key, value, source, source_ref, fingerprint, retention_days, expires_at)
              values (:mid, :cid, 'idem_0123456789abcdef', 'preference', 'colour', 'blue', 'user_explicit', 'memory-page-7', repeat('a', 64), 30, now() + interval '30 days')""", mid=memory_id, cid=customer)
    e.customer = customer
    return e


@pytest.mark.integration
def test_suggestions_use_consented_owned_memory_and_current_product(env):
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer)})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["reason"]["code"] == "explicit_colour_match"
    assert item["reason"]["source_provenance"] == ["memory-page-7"]
    assert item["reason"]["product_evidence"]["product_name"] == "Blue Shawl"


@pytest.mark.integration
def test_suggestions_fail_closed_when_consent_is_revoked(env):
    env.sql("update memory_consents set granted = false where customer_id = :id", id=env.customer)
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer)})
    assert response.status_code == 200 and response.json()["items"] == []


@pytest.mark.integration
def test_suggestions_fail_closed_for_stale_catalogue(env):
    env.sql("update products set updated_at = now() - interval '25 hours' where slug = 'blue-shawl'")
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer)})
    assert response.status_code == 200 and response.json()["items"] == []
