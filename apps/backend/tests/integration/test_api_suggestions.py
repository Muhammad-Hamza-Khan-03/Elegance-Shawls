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
    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "recommendations_enabled", True)
    monkeypatch.setattr(settings, "recommendations_synthetic_only", True)
    monkeypatch.setattr(settings, "recommendations_experiment_enabled", True)
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
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["reason"]["code"] == "explicit_colour_match"
    assert item["reason"]["source_provenance"] == [f"memory:{item['reason']['source_memory_ids'][0]}"]
    assert "memory-page-7" not in response.text
    assert item["reason"]["product_evidence"]["product_name"] == "Blue Shawl"


@pytest.mark.integration
def test_suggestions_fail_closed_when_consent_is_revoked(env):
    env.sql("update memory_consents set granted = false where customer_id = :id", id=env.customer)
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert response.status_code == 200 and response.json()["items"] == []


@pytest.mark.integration
def test_impression_requires_previously_issued_result_set(env):
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    item = response.json()["items"][0]
    evidence = item["reason"]["product_evidence"]
    impression = {
        "recommendation_id": item["id"],
        "product_id": item["product_id"],
        "variant_id": evidence["variant_id"],
        "request_id": "recomputed-but-unissued",
        "position": 0,
        "context": "recommendation_grid",
        "experiment_arm": response.json()["experiment_arm"],
        "preference_version": 1,
        "catalogue_revision": evidence["product_revision"],
        "source_memory_ids": item["reason"]["source_memory_ids"],
    }
    rejected = env.client.post("/v1/me/suggestions/impressions", json=impression,
                               headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert rejected.status_code == 422
    assert "not server-issued" in rejected.json()["detail"]

    impression["request_id"] = response.json()["request_id"]
    accepted = env.client.post("/v1/me/suggestions/impressions", json=impression,
                               headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert accepted.status_code == 204

    issued_after = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"}).json()
    env.sql("update memory_items set status = 'deleted', key = null, value = null, reason = null, source_ref = null, fingerprint = null, deleted_at = now() where customer_id = :id", id=env.customer)
    stale = dict(impression, request_id=issued_after["request_id"])
    deleted = env.client.post("/v1/me/suggestions/impressions", json=stale,
                              headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert deleted.status_code == 422
    assert "no longer current" in deleted.json()["detail"]


@pytest.mark.integration
def test_impression_position_must_match_issued_result_order(env):
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    payload = response.json()
    item = payload["items"][0]
    evidence = item["reason"]["product_evidence"]
    impression = {
        "recommendation_id": item["id"],
        "product_id": item["product_id"],
        "variant_id": evidence["variant_id"],
        "request_id": payload["request_id"],
        "position": 1,
        "context": "recommendation_grid",
        "experiment_arm": payload["experiment_arm"],
        "preference_version": 1,
        "catalogue_revision": evidence["product_revision"],
        "source_memory_ids": item["reason"]["source_memory_ids"],
    }
    rejected = env.client.post("/v1/me/suggestions/impressions", json=impression,
                               headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert rejected.status_code == 422
    assert "position" in rejected.json()["detail"]

    impression["position"] = 0
    accepted = env.client.post("/v1/me/suggestions/impressions", json=impression,
                               headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert accepted.status_code == 204


@pytest.mark.integration
def test_regrant_invalidates_an_old_issued_result_set(env):
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    payload = response.json()
    item = payload["items"][0]
    evidence = item["reason"]["product_evidence"]
    impression = {
        "recommendation_id": item["id"],
        "product_id": item["product_id"],
        "variant_id": evidence["variant_id"],
        "request_id": payload["request_id"],
        "position": 0,
        "context": "recommendation_grid",
        "experiment_arm": payload["experiment_arm"],
        "preference_version": 1,
        "catalogue_revision": evidence["product_revision"],
        "source_memory_ids": item["reason"]["source_memory_ids"],
    }
    env.sql("update memory_consents set granted = false, changed_at = now() where customer_id = :id", id=env.customer)
    env.sql("update memory_consents set granted = true, changed_at = now() + interval '1 second' where customer_id = :id", id=env.customer)
    rejected = env.client.post("/v1/me/suggestions/impressions", json=impression,
                               headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert rejected.status_code == 422
    assert "consent" in rejected.json()["detail"]


@pytest.mark.integration
def test_synthetic_subject_is_required_when_synthetic_only_even_without_experiment(env, monkeypatch):
    monkeypatch.setattr(settings, "recommendations_experiment_enabled", False)
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": "synthetic:wrong-customer"})
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.integration
def test_suggestions_fail_closed_for_stale_catalogue(env):
    env.sql("update products set updated_at = now() - interval '25 hours' where slug = 'blue-shawl'")
    response = env.client.get("/v1/me/suggestions", headers={"X-Test-Customer": str(env.customer), "X-Synthetic-Subject": f"synthetic:{env.customer}"})
    assert response.status_code == 200 and response.json()["items"] == []
