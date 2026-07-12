import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from configuration.config import settings
from models.product_model import build_product_document
from schemas.product_schema import ProductCreateSchema
from security.admin_auth import require_admin_api_key


def product_payload() -> dict:
    return {
        "name": "Classic Pashmina",
        "slug": "classic-pashmina",
        "cover_image_url": "https://images.example.com/cover.jpg",
        "category": "shawls",
        "material": "Pashmina blend",
        "item_number": "ES-001",
        "variants": [{
            "name": "Burgundy", "color": "Burgundy", "size": "Free Size",
            "image_url": "https://images.example.com/burgundy.jpg",
            "price": 4500, "currency": "pkr", "stock": 4,
        }],
    }


def test_contract_normalizes_defaults_and_builds_complete_document():
    product = ProductCreateSchema.model_validate(product_payload())
    document = build_product_document(product.model_dump(mode="json"))
    assert product.price == 4500
    assert product.currency == "PKR"
    assert product.images == [product.cover_image_url]
    assert document["category"] == "shawls"
    assert document["status"] == "active"
    assert document["is_active"] is True
    assert document["variants"][0]["stock"] == 4


@pytest.mark.parametrize("slug", ["Bad Slug", "bad--slug", "-bad", "bad_"])
def test_contract_rejects_unsafe_slugs(slug: str):
    payload = product_payload()
    payload["slug"] = slug
    with pytest.raises(ValidationError):
        ProductCreateSchema.model_validate(payload)


def test_contract_rejects_unknown_fields():
    payload = product_payload()
    payload["unreviewed_field"] = "must not be silently discarded"
    with pytest.raises(ValidationError):
        ProductCreateSchema.model_validate(payload)


@pytest.mark.asyncio
async def test_admin_auth_fails_closed_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    with pytest.raises(HTTPException) as error:
        await require_admin_api_key("anything")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_admin_auth_rejects_invalid_and_accepts_valid_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "a-long-production-secret")
    with pytest.raises(HTTPException) as error:
        await require_admin_api_key("wrong")
    assert error.value.status_code == 401
    assert await require_admin_api_key("a-long-production-secret") is None
