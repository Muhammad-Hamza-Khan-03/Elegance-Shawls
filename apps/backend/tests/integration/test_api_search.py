"""POST /v1/search on real PostgreSQL: hard constraints, paging, public visibility, and no writes."""
import json
from pathlib import Path

import pytest

from routes.search_routes import router as search_router
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant

EVALS = Path(__file__).resolve().parents[4] / "evals"
TABLES = ("products", "variants", "staged_products", "events", "ingestion_jobs")


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    env = ApiEnv(migrated_url, monkeypatch)
    env.app.include_router(search_router)
    return env


def add(env, slug, name, category, variants, status="active", **extra):
    body = {**payload(slug), "name": name, "category": category, "status": status, "variants": variants, **extra}
    assert env.client.post("/products/admin/", json=body, headers=H).status_code == 201


def counts(env):
    return [env.sql(f"SELECT count(*), coalesce(max(revision), 0) FROM {t}" if t == "products" else f"SELECT count(*), 0 FROM {t}")[0] for t in TABLES]


def seed(env):
    add(env, "brown-stole", "Brown Pashmina Stole", "stoles", [variant("Brown", price=3500)])
    add(env, "black-shawl", "Black Wool Shawl", "shawls",
        [variant("Black", price=9000, stock=5), variant("Brown", price=3000, stock=0)])
    add(env, "draft-stole", "Draft Brown Stole", "stoles", [variant("Brown", price=1000)], status="draft")


def slugs(body):
    return [item["product"]["slug"] for item in body["items"]]


def test_constraints_roman_urdu_and_visibility(env):
    seed(env)
    post = lambda q, **p: env.client.post("/v1/search", json={"q": q, **p})
    body = post("brown stole under 4000").json()
    assert slugs(body) == ["brown-stole"] and body["filters"] == {"category": "stoles", "colors": ["brown"], "max_price": 4000}
    assert slugs(post("bhoora stole 4000 se kam").json()) == ["brown-stole"]       # draft never listed
    assert slugs(post("بھورا اسٹول").json()) == ["brown-stole"]
    # black AND under 4000 AND in stock exist in the product, but on different variants
    assert post("black shawl under 4000 in stock").json()["items"] == []
    hit = post("black shawl in stock").json()["items"][0]
    assert hit["matched_variant_ids"] == [next(v["_id"] for v in hit["product"]["variants"] if v["color"] == "Black")]
    assert post("shawl not over 1000").json()["unsupported"]


def test_paging_and_malformed_input(env):
    seed(env)
    post = lambda **body: env.client.post("/v1/search", json=body)
    first = post(limit=1).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = post(limit=1, cursor=first["next_cursor"]).json()
    assert slugs(first) != slugs(second) and second["next_cursor"] is None
    assert post(cursor="garbage").status_code == 400
    assert post(limit=0).status_code == 422 and post(limit=1000).status_code == 422
    assert post(q="x" * 201).status_code == 422 and post(unknown=1).status_code == 422
    assert env.client.post("/v1/search", content=b"{").status_code == 422
    assert post().status_code == 200 and post(q="  ").status_code == 200
    assert env.client.get("/v1/search").status_code == 405         # POST is the contract


def test_search_never_writes(env):
    seed(env)
    before = counts(env)
    for q in ("brown stole", "", "zzzz", "'; DROP TABLE products;--", "shawl not over 1000", "100%_"):
        assert env.client.post("/v1/search", json={"q": q}).status_code == 200
    assert counts(env) == before


def test_database_matching_agrees_with_the_offline_reference_on_every_eval_case(env):
    """The SQL narrowing must never lose a match: replay the whole eval dataset against PostgreSQL."""
    for raw in json.loads((EVALS / "fixtures/retrieval_catalogue.json").read_text(encoding="utf-8")):
        variants = [variant(v["name"], color=v["color"], price=v["price"], currency=v["currency"], stock=v["stock"])
                    for v in raw["variants"]]
        add(env, f"fx-{raw['id']}", raw["name"], raw["category"], variants, status=raw["status"], material=raw["material"],
            main_description=raw["description"], item_number=raw["item_number"])
    for line in (EVALS / "datasets/retrieval_constraints.jsonl").read_text(encoding="utf-8").splitlines():
        case, got, cursor = json.loads(line), set(), None
        while True:                                   # follow the cursor to the end, two results at a time
            body = env.client.post("/v1/search", json={"q": case["query"], "limit": 2, "cursor": cursor}).json()
            got |= {item["product"]["slug"].removeprefix("fx-") for item in body["items"]}
            if not (cursor := body["next_cursor"]):
                break
        assert got == set(case["expected_ids"]), case["query"]
