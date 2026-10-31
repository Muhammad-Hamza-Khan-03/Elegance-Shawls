"""Server-side catalogue search and cursor traversal (GET /products/ and GET /v1/search) on PostgreSQL."""
import pytest

from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant


@pytest.fixture
def client(pg_engine_factory, migrated_url, monkeypatch):
    return ApiEnv(migrated_url, monkeypatch).client


def make(client, slug, *, status="active", **over):
    body = {**payload(slug), **over}
    body["status"] = status
    assert client.post("/products/admin/", json=body, headers=H).status_code == 201, slug


def walk(client, path, limit=3, **params):
    slugs, cursor = [], None
    while True:
        page = client.get(path, params={"limit": limit, **params, **({"cursor": cursor} if cursor else {})}).json()
        slugs += [i["slug"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            return slugs


@pytest.mark.parametrize("path", ["/products/", "/v1/search"])
def test_traverses_full_catalogue_beyond_100_without_gaps_or_duplicates(client, path):
    for i in range(105):
        make(client, f"bulk-{i:03d}")
    slugs = walk(client, path, limit=100)
    assert len(slugs) == 105 and len(set(slugs)) == 105


def test_search_matches_name_color_material_and_item_number_case_insensitively(client):
    make(client, "a-one", name="Kashmiri Wool Stole", material="Pure Merino")
    make(client, "b-two", name="Plain Shawl", variants=[variant("Camel")])
    make(client, "c-three", name="Other", item_number="ES-777")
    assert walk(client, "/v1/search", q="KASHMIRI") == ["a-one"]
    assert walk(client, "/v1/search", q="merino") == ["a-one"]
    assert walk(client, "/v1/search", q="camel") == ["b-two"]
    assert walk(client, "/v1/search", q="es-777") == ["c-three"]
    assert walk(client, "/v1/search", q="wool merino") == ["a-one"]      # all terms must match
    assert walk(client, "/v1/search", q="wool camel") == []


def test_search_paginates_with_the_filter_applied_and_treats_wildcards_literally(client):
    for i in range(5):
        make(client, f"hit-{i}", name="Wool Hit")
    make(client, "miss", name="Silk")
    assert len(walk(client, "/v1/search", limit=2, q="wool")) == 5
    assert walk(client, "/v1/search", q="%") == [] and walk(client, "/v1/search", q="_") == []


def test_search_only_sees_public_products(client):
    make(client, "live-wool", name="Wool")
    make(client, "draft-wool", name="Wool", status="draft")
    make(client, "archived-wool", name="Wool", status="archived")
    assert walk(client, "/v1/search", q="wool") == ["live-wool"]


def test_search_responses_keep_the_list_contract_and_cursor_errors(client):
    make(client, "only", name="Wool")
    body = client.get("/v1/search", params={"q": "wool"}).json()
    assert set(body) == {"items", "next_cursor"} and "_id" in body["items"][0]
    assert client.get("/v1/search").json() == client.get("/products/").json()
    assert client.get("/products/", params={"q": "nomatch"}).json() == client.get("/products/").json()  # /products/ ignores q
    assert client.get("/v1/search?cursor=not-valid").status_code == 400
    make(client, "second", name="Wool")
    cursor = client.get("/v1/search", params={"q": "wool", "limit": 1}).json()["next_cursor"]
    assert client.get("/v1/search", params={"cursor": cursor[:-1] + ("0" if cursor[-1] != "0" else "1")}).status_code == 400
    assert client.get("/v1/search?limit=101").status_code == 422
    assert client.get("/products/slug/only").status_code == 200
