"""P1-S1: vocabulary, deterministic query parsing, hard constraints, paging, and the offline retrieval gate."""
import ast
import asyncio
import importlib.util
import inspect
import json
import socket
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from catalog import query as query_module
from catalog import search as search_module
from catalog.query import ParsedQuery, _build, load_vocabulary, normalize, parse_query, tokenize
from catalog.search import MAX_LIMIT, rank

CATALOG = Path(query_module.__file__).parent
EVALS = Path(__file__).resolve().parents[3] / "evals"
spec = importlib.util.spec_from_file_location("run_retrieval_evals", EVALS / "run_retrieval_evals.py")
retrieval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retrieval)
CATALOGUE = retrieval.load_catalogue(EVALS / "fixtures" / "retrieval_catalogue.json")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nothing in this module may open a socket: parsing and matching are pure."""
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ---- vocabulary -------------------------------------------------------------------------------

def test_vocabulary_loads_and_covers_the_three_languages():
    raw = yaml.safe_load((CATALOG / "vocab.yaml").read_text(encoding="utf-8"))
    for section in ("categories", "colors"):               # every category and colour has Urdu script AND Roman Urdu terms
        for value, phrases in raw[section].items():
            assert any("؀" <= c <= "ۿ" for p in phrases for c in p), value
            assert len([p for p in phrases if p.isascii()]) >= 2 or section == "colors", value
    assert set(raw["categories"]) == {"shawls", "stoles", "scarves"}   # equals the products.category check
    assert load_vocabulary().longest >= 2


def test_ambiguous_vocabulary_is_rejected():
    raw = yaml.safe_load((CATALOG / "vocab.yaml").read_text(encoding="utf-8"))
    raw["colors"]["white"].append("shawl")      # "shawl" is already a category
    with pytest.raises(ValueError, match="ambiguous"):
        _build(raw)


def test_normalisation_unifies_digits_marks_and_case():
    assert normalize("۴۰۰۰") == "4000" == normalize("٤٠٠٠")
    assert tokenize("Rs. 4,000/-") == ["rs", "4000"]
    assert normalize("کَالا") == normalize("کالا")          # diacritic removed
    assert tokenize("  ") == [] and tokenize("!!!") == []


# ---- parser -----------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("brown stole under 4000", {"category": "stoles", "colors": ["brown"], "max_price": 4000}),
    ("bhoora shawal 4000 se kam", {"category": "shawls", "colors": ["brown"], "max_price": 4000}),
    ("بھورا شال ۴۰۰۰ سے کم", {"category": "shawls", "colors": ["brown"], "max_price": 4000}),
    ("gulabi shawl, white nahi", {"category": "shawls", "colors": ["pink"], "exclude_colors": ["white"]}),
    ("red scarf not under 1000", {"category": "scarves", "colors": ["red"], "min_price": 1000}),
    ("shawl between 9000 and 5000", {"category": "shawls", "min_price": 5000, "max_price": 9000}),
    ("shawl under Rs 4,000", {"category": "shawls", "max_price": 4000}),
    ("stole under 2000 under 1500", {"category": "stoles", "max_price": 1500}),      # both hold: the stricter wins
    ("available shawls", {"category": "shawls", "in_stock": True}),
    ("show me everything", {}),
])
def test_parser_extracts_hard_constraints(text, expected):
    parsed = parse_query(text)
    assert parsed.filters() == expected and not parsed.unsupported and not parsed.text


def test_parser_is_deterministic_and_total_on_hostile_input():
    for text in [None, "", "   ", "\x00‮​", "ا" * 5000, "under", "between 1 and", "9" * 50 + " se kam", "'; DROP TABLE products;--"]:
        assert parse_query(text) == parse_query(text)
    assert parse_query("shawl under " + "9" * 50).unsupported == ("price out of range",)


def test_unrepresentable_queries_are_flagged_not_guessed():
    assert parse_query("not over 1000").unsupported
    assert parse_query("not in stock").unsupported
    assert parse_query("pashmina not wool").unsupported
    assert parse_query("shawl under").unsupported == ("price operator without a number",)
    assert parse_query("stole 3000").text == ("3000",)      # a bare number is never read as a price


def test_existing_filter_parsing_dataset_agrees_except_for_the_new_materials_facet():
    for line in (EVALS / "datasets" / "filter_parsing.jsonl").read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        got = {k: v for k, v in parse_query(case["query"]).filters().items() if k != "materials"}
        assert got == case["expected"], case["query"]


# ---- hard constraints -------------------------------------------------------------------------

def ids(text):
    return {h.product.id for h in rank(parse_query(text), CATALOGUE)}


def test_all_variant_constraints_must_hold_on_the_same_variant():
    assert ids("black shawl in stock") == {"p02", "p09"}
    assert ids("black shawl under 4000 in stock") == set()     # p09 is black AND cheap AND stocked, but never on one variant
    hit = next(h for h in rank(parse_query("black shawl in stock"), CATALOGUE) if h.product.id == "p02")
    assert hit.variant_ids == ("p02a",)                        # the sold-out black variant is not offered


def test_unknown_values_never_satisfy_a_constraint():
    assert ids("navy stole") == set()                          # colour not recorded
    assert "p03" not in ids("wool shawl")                      # material not recorded
    assert "p08" not in ids("stole not black")                 # cannot prove the colour is not black
    assert "p10" not in ids("shawl under 5000")                # USD price is not comparable to PKR


def test_constraints_are_not_relaxed_when_nothing_matches():
    assert ids("pashmina shawl between 1000 and 2000") == set()
    assert ids("zzzzzz") == set()
    assert ids("shawl not over 1000") == set()


def test_only_active_products_are_returned():
    assert "p07" not in ids("") and ids("red scarf") == set()


# ---- ordering and pagination ------------------------------------------------------------------

def make_products(n):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [SimpleNamespace(
        id=str(uuid.UUID(int=i)), name=f"Shawl {i}", category="shawls", status="active", material=None,
        main_description=None, item_number=None, created_at=base + timedelta(minutes=i % 3),   # ties on purpose
        variants=[SimpleNamespace(id=f"v{i}", name="x", color="Black", price=100, currency="PKR", stock=1, is_active=True)])
        for i in range(n)]


def test_order_is_total_and_independent_of_input_order():
    products = make_products(12)
    forward = [h.product.id for h in rank(parse_query("shawl"), products)]
    assert forward == [h.product.id for h in rank(parse_query("shawl"), list(reversed(products)))]
    assert len(set(forward)) == 12
    assert forward == [p.id for p in sorted(products, key=search_module.key, reverse=True)]   # newest first, id tie-break


def fake_fetch(products, calls=None):
    ordered = sorted(products, key=search_module.key, reverse=True)

    async def fetch(after, n):
        if calls is not None:
            calls.append(n)
        rest = [p for p in ordered if after is None or search_module.key(p) < after]
        return rest[:n]

    return fetch


def collect(products, text, **kwargs):
    """Follow next positions until exhausted; returns the pages."""
    q, after, pages = parse_query(text), None, []
    while True:
        hits, after = asyncio.run(search_module.search_page(fake_fetch(products), q, after=after, **kwargs))
        pages.append([h.product.id for h in hits])
        if after is None:
            return pages


@pytest.mark.parametrize("batch,max_scan", [(200, 2000), (3, 2000), (2, 5), (1, 1)])
def test_pages_partition_the_results_exactly_whatever_the_scan_budget(batch, max_scan):
    products = make_products(11)
    for p in products[::2]:
        p.name = "Plain Stole"       # every other product is filtered out, so budgets run dry mid-page
    whole = [h.product.id for h in rank(parse_query("shawl"), products)]
    pages = collect(products, "shawl", limit=4, batch=batch, max_scan=max_scan)
    assert [i for page in pages for i in page] == whole
    assert all(len(page) <= 4 for page in pages)


def test_scan_budget_bounds_work_and_leaves_a_continuation():
    products, calls = make_products(30), []
    hits, after = asyncio.run(search_module.search_page(
        fake_fetch(products, calls), parse_query("zzzzzz"), batch=4, max_scan=10))
    assert hits == [] and after is not None and sum(calls) == 10      # short (empty) page, but not "no results"
    assert asyncio.run(search_module.search_page(fake_fetch(products), parse_query("zzzzzz")))[1] is None   # exhausted


def test_limit_is_clamped_and_unsupported_queries_never_fetch():
    products = make_products(MAX_LIMIT + 5)
    assert len(asyncio.run(search_module.search_page(fake_fetch(products), parse_query(""), limit=10_000))[0]) == MAX_LIMIT
    assert len(asyncio.run(search_module.search_page(fake_fetch(products), parse_query(""), limit=0))[0]) == 1
    calls = []
    assert asyncio.run(search_module.search_page(fake_fetch(products, calls), parse_query("not over 1000"))) == ([], None)
    assert calls == []


# ---- isolation --------------------------------------------------------------------------------

def test_catalog_package_has_no_provider_network_or_database_imports():
    banned = {"httpx", "requests", "urllib", "socket", "litellm", "openai", "llm", "sqlalchemy", "redis", "database"}
    for path in CATALOG.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not {n.split(".")[0] for n in names} & banned, path.name


def test_search_fetch_and_route_only_read():
    from repositories.products import search_batch
    sources = {"search_batch": inspect.getsource(search_batch),
               "search_routes": (CATALOG.parent / "routes/search_routes.py").read_text(encoding="utf-8")}
    for name, source in sources.items():
        for forbidden in (".add(", ".add_all(", ".delete(", "insert(", "update(", ".commit(", ".flush(", "begin(", "set_status", "publish"):
            assert forbidden not in source, (name, forbidden)


# ---- the offline retrieval gate ---------------------------------------------------------------

def test_retrieval_gate_passes_on_the_shipped_non_empty_dataset():
    cases = [json.loads(l) for l in (EVALS / "datasets" / "retrieval_constraints.jsonl").read_text(encoding="utf-8").splitlines()]
    result = retrieval.run(cases, CATALOGUE)
    assert result["status"] == "pass", result["failures"]
    assert len(cases) >= 30 and {c["lang"] for c in cases} == {"en", "ur", "roman_ur"}
    assert any(not c["expected_ids"] for c in cases) and any(c["unsupported"] for c in cases)


def test_retrieval_gate_fails_on_a_violation_and_never_passes_empty(tmp_path):
    wrong = [{"id": "x", "lang": "en", "query": "brown stole under 4000", "filters": None, "unsupported": False,
              "expected_ids": ["p02"]}]
    assert retrieval.run(wrong, CATALOGUE)["status"] == "fail"
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "retrieval_constraints.jsonl").write_text("")
    assert retrieval.main(["--root", str(tmp_path)]) == 2


def test_global_release_gate_is_untouched_by_the_retrieval_gate():
    spec = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
    run_evals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_evals)
    assert run_evals.main(["--release-ready"]) == 3


def test_post_search_uses_the_public_rate_limit_not_the_admin_one(monkeypatch):
    from security import rate_limit
    monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
    monkeypatch.setattr(rate_limit.settings, "admin_rate_limit_per_minute", 1)
    monkeypatch.setattr(rate_limit.settings, "public_rate_limit_per_minute", 5)

    async def ok(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    middleware = rate_limit.RateLimitMiddleware(ok)

    async def call(method, path):
        status = []

        async def send(message):
            status.append(message["status"]) if message["type"] == "http.response.start" else None

        scope = {"type": "http", "method": method, "path": path, "headers": [], "query_string": b"",
                 "client": ("9.9.9.9", 1), "scheme": "http", "server": ("t", 80)}
        await middleware(scope, None, send)
        return status[0]

    async def run():
        return ([await call("POST", "/v1/search") for _ in range(3)],
                [await call("POST", "/products/admin/") for _ in range(2)])

    search, other = asyncio.run(run())
    assert search == [200, 200, 200] and other == [200, 429]
