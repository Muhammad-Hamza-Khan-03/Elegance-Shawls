import pytest
from pydantic import ValidationError

from schemas.product_schema import ProductCreateSchema


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


def test_contract_normalizes_defaults():
    product = ProductCreateSchema.model_validate(product_payload())
    assert product.price == 4500
    assert product.currency == "PKR"
    assert product.images == [product.cover_image_url]
    assert product.category == "shawls"
    assert product.status == "active"
    assert product.variants[0].stock == 4


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


@pytest.mark.parametrize("category", ["shawls", "stoles", "scarves"])
def test_contract_accepts_every_first_class_category(category: str):
    product = ProductCreateSchema.model_validate({**product_payload(), "category": category})
    assert product.category == category


@pytest.mark.parametrize("category", ["scarf", "Scarves", "wraps", "wallets"])
def test_contract_rejects_non_canonical_categories(category: str):
    with pytest.raises(ValidationError):
        ProductCreateSchema.model_validate({**product_payload(), "category": category})
