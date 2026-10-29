"""Pure, read-only catalogue matching: hard constraints, lexical text match, deterministic paging.

A product matches only when ONE active variant satisfies every variant-level constraint (colour,
price, stock) and the product satisfies the product-level ones (category, material, text). Unknown
values (no colour, no material) never satisfy a constraint that needs them. Nothing is relaxed.

Order is the catalogue's own: (created_at, id) descending, so the cursor is the house keyset cursor
(utils/pagination.py). Paging is a bounded scan: the database narrows candidates with conservative
predicates (repositories.products.search_batch), `evaluate` stays the exact authority, and at most
MAX_SCAN rows are examined per request. If that budget runs out the page is short but `next_cursor`
is set, so a client keeps paging until it is null; results are never silently dropped.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from catalog.query import ParsedQuery, Vocabulary, load_vocabulary, tokenize

CURRENCY = "PKR"  # prices are only comparable in the catalogue currency
MAX_LIMIT = 50
BATCH = 200       # rows fetched per database round trip
MAX_SCAN = 2000   # rows examined per request


@dataclass(frozen=True)
class Hit:
    product: Any                      # a Product row, or any object with the same attributes
    variant_ids: tuple                # every active variant that satisfies all variant-level constraints


def key(product) -> tuple:
    return product.created_at, product.id


def _variant_ok(v, q: ParsedQuery, vocab: Vocabulary) -> bool:
    if not v.is_active:
        return False
    if q.colors or q.exclude_colors:
        colors = vocab.canonical("color", v.color)
        # Excluding needs a KNOWN colour: an unrecognised or missing one cannot be proven not to be excluded.
        if not colors or (q.colors and not colors & set(q.colors)) or colors & set(q.exclude_colors):
            return False
    if q.min_price is not None or q.max_price is not None:
        if v.currency != CURRENCY or (q.min_price is not None and v.price < q.min_price) \
                or (q.max_price is not None and v.price > q.max_price):
            return False
    return not q.in_stock or v.stock > 0


def _text_ok(product, q: ParsedQuery) -> bool:
    """Every unrecognised query token must appear as a whole word in the product's text."""
    words = set(tokenize(" ".join(filter(None, [product.name, product.main_description, product.material,
                                                product.item_number, *[v.name for v in product.variants]]))))
    return all(t in words for t in q.text)


def evaluate(q: ParsedQuery, product, vocab: Vocabulary | None = None) -> Hit | None:
    vocab = vocab or load_vocabulary()
    if q.unsupported or product.status != "active":
        return None
    if q.categories and product.category not in q.categories:
        return None
    if q.materials and not vocab.canonical("material", product.material) & set(q.materials):
        return None
    if not _text_ok(product, q):
        return None
    ids = tuple(v.id for v in product.variants if _variant_ok(v, q, vocab))
    return Hit(product, ids) if ids else None


def rank(q: ParsedQuery, products, vocab: Vocabulary | None = None) -> list[Hit]:
    """All matching hits in catalogue order (newest first, id as the tie-break)."""
    ordered = sorted(products, key=key, reverse=True)
    return [h for p in ordered if (h := evaluate(q, p, vocab))]


Fetch = Callable[[tuple | None, int], Awaitable[list]]   # (after key, n) -> next n products in catalogue order


async def search_page(fetch: Fetch, q: ParsedQuery, *, limit: int = 20, after: tuple | None = None,
                      vocab: Vocabulary | None = None, batch: int = BATCH,
                      max_scan: int = MAX_SCAN) -> tuple[list[Hit], tuple | None]:
    """(one page of hits, key to continue after or None when the catalogue is exhausted)."""
    limit = max(1, min(limit, MAX_LIMIT))
    if q.unsupported:
        return [], None
    hits: list[Hit] = []
    scanned, last = 0, after
    while scanned < max_scan:
        n = min(batch, max_scan - scanned)
        rows = await fetch(last, n)
        for product in rows:
            scanned += 1
            last = key(product)
            if hit := evaluate(q, product, vocab):
                hits.append(hit)
                if len(hits) > limit:                      # one more exists: continue after the last returned hit
                    return hits[:limit], key(hits[limit - 1].product)
        if len(rows) < n:
            return hits, None
    return hits, last                                      # scan budget spent: short page, more may follow
