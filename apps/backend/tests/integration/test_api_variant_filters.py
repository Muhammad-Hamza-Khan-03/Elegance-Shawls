"""Variant-level AND filters on /v1/search: one purchasable variant must satisfy colour, price and stock together."""
import itertools

import pytest

from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

# (slug, variants) - each variant is (color, name, price, stock)
CATALOGUE = {
    "red-cheap-oos-blue-dear-stock": [("Red", "Red", 1000, 0), ("Blue", "Blue", 9000, 5)],   # cross-variant trap
    "red-dear-stock": [("Red", "Red", 9000, 3)],
    "red-cheap-stock": [("Red", "Red", 1000, 3)],
    "gray-cheap-stock": [("Gray", "Gray", 1200, 2)],
    "unlabelled-camel-name": [(None, "Camel", 1500, 2)],
    "unknown-colour-red-name": [("Turquoise", "Red", 1500, 2)],
}


@pytest.fixture
def client(pg_engine_factory, migrated_url, monkeypatch):
    c = ApiEnv(migrated_url, monkeypatch).client
    for slug, vs in CATALOGUE.items():
        body = {**payload(slug), "status": "active",
                "variants": [variant(n, color=col, price=p, stock=s) for col, n, p, s in vs]}
        assert c.post("/products/admin/", json=body, headers=H).status_code == 201, slug
    return c


def slugs(client, **params):
    out, cursor = [], None
    while True:
        page = client.get("/v1/search", params={**params, "limit": 2, **({"cursor": cursor} if cursor else {})}).json()
        out += [i["slug"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            return sorted(out)


def test_same_variant_positive_and_cross_variant_negative(client):
    assert slugs(client, colour="red", max_price=2000, in_stock=True) == ["red-cheap-stock"]
    # red-cheap-oos-blue-dear-stock has red AND cheap AND in-stock variants, but never on one variant
    assert "red-cheap-oos-blue-dear-stock" not in slugs(client, colour="red", max_price=2000, in_stock=True)
    assert slugs(client, colour="blue", max_price=2000) == []
    assert slugs(client, colour="red", min_price=5000, in_stock=True) == ["red-dear-stock"]
    assert slugs(client, colour="red", max_price=2000) == ["red-cheap-oos-blue-dear-stock", "red-cheap-stock"]
    assert slugs(client, in_stock=True, max_price=2000) == sorted(["gray-cheap-stock", "red-cheap-stock", "unlabelled-camel-name", "unknown-colour-red-name"])


def test_every_filter_combination_matches_a_python_oracle(client):
    colours, mins, maxs, stocks = ["red", "blue", "grey", "camel", None], [None, 5000], [None, 2000], [False, True]
    for colour, mn, mx, st in itertools.product(colours, mins, maxs, stocks):
        if colour is None and mn is None and mx is None and not st:
            continue
        if mn is not None and mx is not None:
            continue  # contradictory range, rejected with 422 (tested separately)
        want = sorted(
            slug for slug, vs in CATALOGUE.items()
            if any((colour is None or _canon(col, n) == colour) and (mn is None or p >= mn)
                   and (mx is None or p <= mx) and (not st or s > 0) for col, n, p, s in vs))
        params = {k: v for k, v in dict(colour=colour, min_price=mn, max_price=mx, in_stock=st or None).items() if v is not None}
        assert slugs(client, **params) == want, params


def _canon(col, name):
    from utils.colour_vocabulary import resolve
    return resolve(col, name).canonical


def test_synonyms_and_provenance_in_search(client):
    assert slugs(client, colour="gray") == slugs(client, colour="grey") == ["gray-cheap-stock"]
    assert slugs(client, colour="Camel") == ["unlabelled-camel-name"]            # name used only when colour is null
    assert "unknown-colour-red-name" not in slugs(client, colour="red")           # unknown explicit colour is not overridden


def test_invalid_filters_are_rejected_and_no_filter_is_s1_behaviour(client):
    assert client.get("/v1/search", params={"colour": "turquoise"}).status_code == 422
    assert client.get("/v1/search", params={"min_price": 5, "max_price": 1}).status_code == 422
    assert client.get("/v1/search", params={"min_price": -1}).status_code == 422
    assert slugs(client) == sorted(CATALOGUE)
    assert slugs(client, colour="red", q="dear") == ["red-cheap-oos-blue-dear-stock", "red-dear-stock"]  # composes with q


def test_unpublished_products_and_inactive_variants_never_match(client):
    draft = {**payload("draft-red"), "status": "draft", "variants": [variant("Red")]}
    assert client.post("/products/admin/", json=draft, headers=H).status_code == 201
    assert "draft-red" not in slugs(client, colour="red")
