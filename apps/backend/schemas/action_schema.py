"""Canonical M3 action names and strict parameter contracts.

Canonical names are the public/API vocabulary. Persistence continues to use the
legacy names because migration 0013 and existing replay fingerprints depend on
those values.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

CANONICAL_ACTIONS = frozenset({
    "show_products", "open_product", "apply_filters", "add_to_cart", "start_whatsapp_order",
})
LEGACY_ACTIONS = frozenset({"show_product", "start_whatsapp_enquiry", "add_to_cart"})
_CANONICAL_TO_LEGACY = {
    "show_products": "show_product",
    "open_product": "show_product",
    "apply_filters": "show_product",
    "add_to_cart": "add_to_cart",
    "start_whatsapp_order": "start_whatsapp_enquiry",
}
_LEGACY_TO_CANONICAL = {
    "show_product": "open_product",
    "start_whatsapp_enquiry": "start_whatsapp_order",
    "add_to_cart": "add_to_cart",
}


def normalize_action(action: str) -> str:
    """Return the legacy value used by the kernel, storage and fingerprints."""
    try:
        return _CANONICAL_TO_LEGACY[action]
    except KeyError:
        if action in LEGACY_ACTIONS:
            return action
        raise ValueError("unknown action")


def canonical_action_name(action: str) -> str:
    """Return the public vocabulary name for a canonical or legacy alias."""
    try:
        return _LEGACY_TO_CANONICAL[action]
    except KeyError:
        if action in CANONICAL_ACTIONS:
            return action
        raise ValueError("unknown action")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProductFilters(_Strict):
    category: StrictStr | None = None
    colour: StrictStr | None = None
    price_min: StrictInt | None = Field(default=None, ge=0)
    price_max: StrictInt | None = Field(default=None, ge=0)
    size: StrictStr | None = None
    stock_state: Literal["in_stock", "out_of_stock", "any"] | None = None

    @model_validator(mode="after")
    def valid_price_range(self):
        if self.price_min is not None and self.price_max is not None and self.price_min > self.price_max:
            raise ValueError("price_min must not exceed price_max")
        return self


class ShowProductsParams(_Strict):
    query: StrictStr | None = None
    filters: ProductFilters | None = None
    limit: StrictInt = Field(default=20, ge=1, le=100)
    cursor: StrictStr | None = None


class OpenProductParams(_Strict):
    product_id: StrictStr | None = None
    slug: StrictStr | None = None
    expected_revision: StrictInt | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def exactly_one_identifier(self):
        if (self.product_id is None) == (self.slug is None):
            raise ValueError("exactly one of product_id or slug is required")
        return self


class ApplyFiltersParams(ProductFilters):
    cursor: StrictStr | None = None


class ActionItemParams(_Strict):
    product_id: StrictStr
    variant_id: StrictStr
    quantity: StrictInt = Field(ge=1, le=1000)
    expected_revision: StrictInt = Field(ge=1)
    expected_unit_price: StrictInt = Field(ge=0)
    currency: Literal["PKR"]


class AddToCartParams(ActionItemParams):
    pass


class StartWhatsAppOrderParams(_Strict):
    items: list[ActionItemParams] = Field(min_length=1, max_length=10)


def validate_runtime_params(action: str, params: Any) -> dict:
    """Validate public action payloads before they reach a runtime entry point."""
    models = {
        "show_products": ShowProductsParams,
        "open_product": OpenProductParams,
        "apply_filters": ApplyFiltersParams,
        "add_to_cart": AddToCartParams,
        "start_whatsapp_order": StartWhatsAppOrderParams,
    }
    try:
        model = models[action]
    except KeyError as exc:
        raise ValueError("unknown action") from exc
    return model.model_validate(params).model_dump(exclude_none=True)
