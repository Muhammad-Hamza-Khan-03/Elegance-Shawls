"""P1-S4c: hybrid fusion, hard-constraint authority, cursor and bounds, offline with repository fakes."""
import asyncio
import socket
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from catalog.query import parse_query
from catalog.search import Hit
from search import hybrid
from search.hybrid import RRF_K, fuse, rrf_score
from search.providers import FakeEmbeddingProvider

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
K = {"k_lexical": 10, "k_semantic": 10, "max_scan": 100}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def variant(color="Brown", price=3000, stock=5, active=True, name="V"):
    return SimpleNamespace(id=uuid.uuid4(), is_active=active, color=color, price=price, stock=stock, currency="PKR", name=name)


def product(n, name="Cozy Stole", category="stoles", status="active", variants=None, material="wool"):
    """n orders catalogue position: a larger n is newer."""
    return SimpleNamespace(id=uuid.UUID(int=n), created_at=T0 + timedelta(days=n), name=name, category=category, status=status,
                           material=material, main_description=None, item_number=None, variants=variants or [variant()])


def fetcher(products):
    calls = []

    async def fetch(after, n):
        calls.append((after, n))
        rows = sorted(products, key=lambda p: (p.created_at, p.id), reverse=True)
        return [p for p in rows if after is None or (p.created_at, p.id) < after][:n]
    fetch.calls = calls
    return fetch


def semantic_of(order):
    """Fake vector branch: nearest-first product ids; distance is the position."""
    async def run(hits, k):
        return {p.id: float(i) for i, p in enumerate(order)}
    return run


def page(products, q, semantic=None, **over):
    return asyncio.run(hybrid.hybrid_page(fetcher(products), parse_query(q), semantic, **{**K, **over}))


def ids(hits):
    return [h.product.id.int for h in hits]


def hit(n):
    return Hit(product(n), ())


# ---- fusion truth table ------------------------------------------------------------------------

def test_rrf_constant_and_truth_table():
    assert RRF_K == 60
    assert rrf_score(1, 1) == round(2 / 61, 12)
    assert rrf_score(1, None) == rrf_score(None, 1) == round(1 / 61, 12)
    assert rrf_score(1, 10) == round(1 / 61 + 1 / 70, 12)
    assert rrf_score(None, None) == 0
    assert rrf_score(1, None) > rrf_score(2, None) > rrf_score(3, None)
    assert rrf_score(2, 2) > rrf_score(1, None)            # agreement of two branches beats one first place


def test_fuse_union_dedupe_and_order():
    a, b, c, d = hit(1), hit(2), hit(3), hit(4)
    fused = fuse([a, b, c], [c, d, a, a])                  # a duplicate inside a branch never counts twice
    assert [h.product.id.int for _, h in fused] == [3, 1, 4, 2]    # c: l3+s1; a: l1+s3; then b(l2) and d(s2) tie on 1/62: newest (d) first
    assert fused[0][0] == rrf_score(3, 1) and fused[1][0] == rrf_score(1, 3) and len({h.product.id for _, h in fused}) == 4


def test_ties_break_by_created_at_then_id_descending():
    older, newer = hit(1), hit(2)
    assert [h.product.id.int for _, h in fuse([older], [newer])] == [2, 1]          # equal score 1/61: newest first
    same_time = [Hit(SimpleNamespace(id=uuid.UUID(int=i), created_at=T0), ()) for i in (7, 9, 8)]
    assert [h.product.id.int for _, h in fuse(same_time, [])][0] == 7               # rank 1 outranks; then...
    tied = fuse([same_time[0]], [same_time[1]])
    assert [h.product.id.int for _, h in tied] == [9, 7]                            # ...id descending on equal time


def test_lexical_only_and_semantic_only_orders():
    a, b = hit(1), hit(2)
    assert [h.product.id.int for _, h in fuse([a, b], [])] == [1, 2]                # lexical rank order kept
    assert [h.product.id.int for _, h in fuse([], [b, a])] == [2, 1]                # semantic rank order kept


# ---- hard constraints are authoritative ---------------------------------------------------------

def test_semantic_cannot_make_an_ineligible_product_eligible():
    good = product(1)
    draft, archived = product(2, status="draft"), product(3, status="archived")
    wrong_category = product(4, category="shawls")
    over_budget = product(5, variants=[variant(price=9000)])
    # the fake vector branch ranks every ineligible product FIRST
    hits, _ = page([good, draft, archived, wrong_category, over_budget], "brown stole under 4000",
                   semantic_of([over_budget, wrong_category, archived, draft, good]))
    assert ids(hits) == [1]


def test_text_words_are_soft_but_filters_are_hard_and_unsupported_returns_nothing():
    wool, silk = product(1, name="Warm Cozy Stole"), product(2, name="Silk Stole")
    only_lexical, _ = page([wool, silk], "stole warm")
    assert ids(only_lexical) == [1]                        # "warm" only matches one; deterministic search would also say 1
    both_via_semantic, _ = page([wool, silk], "stole warm", semantic_of([silk, wool]))
    assert set(ids(both_via_semantic)) == {1, 2}           # the vector branch adds a candidate; the filters still hold
    assert page([wool], "stole not over 1000")[0] == []    # unsupported: nothing, no semantic widening
    assert page([wool], "shawl")[0] == []                  # category filter excludes the stole despite the semantic branch
    assert page([wool], "shawl", semantic_of([wool]))[0] == []


def test_same_variant_ids_are_preserved_and_must_satisfy_every_constraint():
    black_pricey, brown_cheap = variant("Black", 9000), variant("Brown", 3000)
    split = product(1, variants=[black_pricey, brown_cheap])
    assert page([split], "black stole under 4000", semantic_of([split]))[0] == []   # no ONE variant is black AND cheap
    two = [variant("Brown", 3000), variant("Brown", 3500), variant("Black", 3000)]
    hits, _ = page([product(2, variants=two)], "brown stole under 4000", semantic_of([product(2)]))
    assert hits[0].variant_ids == (two[0].id, two[1].id)


def test_lexical_branch_without_free_words_is_catalogue_order():
    hits, _ = page([product(1), product(2), product(3)], "stole")
    assert ids(hits) == [3, 2, 1]


# ---- paging and cursor --------------------------------------------------------------------------

def test_pages_continue_deterministically_with_no_duplicates_or_gaps():
    catalogue = [product(n, name=f"Cozy Stole {n}") for n in range(1, 8)]
    order = semantic_of([catalogue[i] for i in (3, 0, 6, 1, 5, 2, 4)])
    full, _ = page(catalogue, "cozy stole", order, limit=50)
    seen, after = [], None
    for _ in range(10):
        hits, after = page(catalogue, "cozy stole", order, limit=3, after=after)
        seen += ids(hits)
        if after is None:
            break
    assert seen == ids(full) and len(seen) == len(set(seen)) == 7
    assert page(catalogue, "cozy stole", order, limit=3)[0] == page(catalogue, "cozy stole", order, limit=3)[0]   # repeatable


def test_candidate_window_is_bounded_and_documented():
    """Tradeoff: only K per branch and max_scan rows are considered; the rest is out of the window, never promoted."""
    catalogue = [product(n, name=f"Cozy Stole {n}") for n in range(1, 21)]
    hits, _ = page(catalogue, "cozy stole", None, limit=50, k_lexical=5)
    assert ids(hits) == [20, 19, 18, 17, 16]                             # lexical K=5, no semantic branch
    near = semantic_of([catalogue[0], catalogue[1]])
    hits, _ = page(catalogue, "cozy stole", near, limit=50, k_lexical=5, k_semantic=1)
    assert set(ids(hits)) == {20, 19, 18, 17, 16, 1}                     # union <= K_lex + K_sem
    fetch = fetcher(catalogue)
    hits = asyncio.run(hybrid.eligible_hits(fetch, parse_query("stole"), max_scan=7, batch=3))
    assert len(hits) == 7 and sum(n for _, n in fetch.calls) == 7        # never examines more than max_scan rows


def test_cursor_round_trip_and_rejections():
    parsed = parse_query("cozy stole under 4000")
    version, qhash = hybrid.search_version(FakeEmbeddingProvider(), "idx-1"), hybrid.query_hash("cozy stole under 4000", parsed, 10, 10, 100)
    pos = (rrf_score(1, 2), T0, uuid.UUID(int=5))
    cursor = hybrid.encode_cursor(pos, version=version, qhash=qhash)
    assert hybrid.decode_cursor(cursor, version=version, qhash=qhash) == pos
    other = lambda q, kl=10: hybrid.query_hash(q, parse_query(q), kl, 10, 100)
    bad_version = hybrid.search_version(FakeEmbeddingProvider(), "idx-2")
    body, _, checksum = cursor.partition(".")
    for bad in (cursor[:-1] + ("0" if cursor[-1] != "0" else "1"), body, body + ".", f"{body}x.{checksum}", "", "a.b.c", "x" * 600,
                cursor + "." + checksum):
        with pytest.raises(ValueError):
            hybrid.decode_cursor(bad, version=version, qhash=qhash)
    for kwargs in ({"version": version, "qhash": other("cozy stole under 5000")},          # changed filter
                   {"version": version, "qhash": other("silk stole under 4000")},          # changed query
                   {"version": version, "qhash": other("cozy stole under 4000", 11)},      # changed bound
                   {"version": bad_version, "qhash": qhash},                               # changed index version
                   {"version": hybrid.search_version(None, "idx-1"), "qhash": qhash}):     # semantic branch gone
        with pytest.raises(ValueError):
            hybrid.decode_cursor(cursor, **kwargs)
    assert hybrid.query_hash("Cozy  STOLE under 4000", parsed, 10, 10, 100) == qhash       # normalised, not byte-compared


def test_deterministic_and_hybrid_cursors_are_not_interchangeable():
    from utils.pagination import decode_cursor, encode_cursor
    parsed = parse_query("stole")
    version, qhash = hybrid.search_version(None, "i"), hybrid.query_hash("stole", parsed, 10, 10, 100)
    with pytest.raises(ValueError):
        hybrid.decode_cursor(encode_cursor(T0, uuid.UUID(int=1)), version=version, qhash=qhash)
    with pytest.raises(ValueError):
        decode_cursor(hybrid.encode_cursor((0.01, T0, uuid.UUID(int=1)), version=version, qhash=qhash))


# ---- query embedding (fake only, disabled-safe) ---------------------------------------------------

def test_query_vector_is_fake_only_bounded_and_disabled_safe():
    run = lambda text, **kw: asyncio.run(hybrid.query_vector(text, **{"enabled": True, "name": "fake", "dimensions": 768, **kw}))
    provider, vec = run("brown stole")
    assert provider.name == "fake" and len(vec) == 768 and vec == run("brown stole")[1]
    assert run("brown stole", enabled=False) == (None, None)
    assert run("   ") == (None, None)
    assert run("brown stole", name="") == (None, None)               # unconfigured: lexical search stays usable
    assert run("brown stole", name="openai") == (None, None)         # unknown provider fails closed, no network
    assert run("x" * 5000) == (None, None)                           # over the provider's length limit
