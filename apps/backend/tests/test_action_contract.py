import pytest
from pydantic import ValidationError

from actions import kernel
from schemas.action_schema import (
    ApplyFiltersParams,
    OpenProductParams,
    ShowProductsParams,
    canonical_action_name,
    normalize_action,
)


def test_public_action_names_normalize_to_legacy_persistence_names():
    assert canonical_action_name("show_product") == "open_product"
    assert canonical_action_name("start_whatsapp_enquiry") == "start_whatsapp_order"
    assert normalize_action("start_whatsapp_order") == "start_whatsapp_enquiry"
    assert normalize_action("add_to_cart") == "add_to_cart"


def test_show_products_schema_is_strict_and_typed():
    params = ShowProductsParams(query="shawl", filters={"category": "shawl"}, limit=20, cursor="abc")
    assert params.limit == 20
    with pytest.raises(ValidationError):
        ShowProductsParams(query="shawl", unknown=True)
    with pytest.raises(ValidationError):
        ShowProductsParams(limit="20")


def test_open_product_requires_exactly_one_identifier():
    assert OpenProductParams(product_id="prod-1").product_id == "prod-1"
    assert OpenProductParams(slug="pashmina-shawl").slug == "pashmina-shawl"
    with pytest.raises(ValidationError):
        OpenProductParams(product_id="prod-1", slug="pashmina-shawl")
    with pytest.raises(ValidationError):
        OpenProductParams()


def test_apply_filters_rejects_unknown_fields_and_invalid_price_range():
    assert ApplyFiltersParams(category="shawl", colour="brown", price_min=1000, price_max=5000,
                              size="large", stock_state="in_stock", cursor="abc")
    with pytest.raises(ValidationError):
        ApplyFiltersParams(stock="in_stock")
    with pytest.raises(ValidationError):
        ApplyFiltersParams(price_min=5000, price_max=1000)


def test_kernel_accepts_canonical_aliases_without_changing_fingerprint_or_ledger_value():
    ctx = kernel.ActionContext("sess-1", {"cart:propose", "enquiry:initiate", "catalogue:read"})
    item = {
        "product_id": "11111111-1111-4111-8111-111111111111",
        "variant_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "quantity": 1,
        "expected_revision": 7,
        "expected_unit_price": 3500,
        "currency": "PKR",
    }
    state = kernel.InMemoryCatalogue({item["product_id"]: {"status": "active", "is_active": True, "revision": 7,
        "variants": [{"id": item["variant_id"], "is_active": True, "price": 3500, "currency": "PKR", "stock": 2}]}})
    legacy = kernel.validate(kernel.ActionProposal("start_whatsapp_enquiry", "idem_0123456789abcdef", {"items": [item]}, ctx), state, kernel.IdempotencyLedger())
    canonical = kernel.validate(kernel.ActionProposal("start_whatsapp_order", "idem_0123456789abcdef", {"items": [item]}, ctx), state, kernel.IdempotencyLedger())
    assert canonical.fingerprint == legacy.fingerprint
    assert canonical.action_type == legacy.action_type == "start_whatsapp_enquiry"
