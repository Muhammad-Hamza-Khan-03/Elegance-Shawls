"""Short-term conversation memory: a follow-up keeps what the customer already asked for.

"grey shawls under 2000", then "under 3000" means grey shawls under 3000; then "grey" -> "red" swaps only the colour.
Stateless on purpose: the browser sends its last few messages as plain text and the server re-parses them with the same deterministic
parser, so nothing the client claims about "filters" is ever trusted, and a tampered history can only change what the customer sees.

Carry rules (fold oldest -> newest):
* a message that names no product word, or names one we sell, is a follow-up; anything else ("delivery kitne din") starts fresh;
* whatever the new message states wins; what it leaves out (colour, budget, in-stock, product type) is kept from before;
* a new product word replaces the old one; a budget that would contradict a kept one replaces it;
* a message the parser needed to ask about contributes nothing.
"""
from dataclasses import replace
from typing import Sequence

from semantic.query_parser import QueryIntent, has_shopping_signal, parse_query

MAX_HISTORY = 3


def _carry(prev: QueryIntent, cur: QueryIntent, text: str) -> tuple[QueryIntent, list[str]]:
    if cur.needs_review or (cur.terms and not has_shopping_signal(text)):
        return cur, []                                              # clarify first / a new topic: nothing carries
    taken: list[str] = []
    colour = cur.colour or prev.colour
    terms = cur.terms or prev.terms
    low = cur.min_price if cur.min_price is not None else prev.min_price
    high = cur.max_price if cur.max_price is not None else prev.max_price
    if low is not None and high is not None and low > high:          # the newer statement wins a conflict
        low, high = (cur.min_price, high) if cur.min_price is not None else (None, high)
        if low is not None and high < low:
            high = cur.max_price
    if cur.colour is None and prev.colour:
        taken.append(f"colour {prev.colour}")
    if not cur.terms and prev.terms:
        taken.append(" ".join(prev.terms))
    if cur.max_price is None and high is not None and prev.max_price == high:
        taken.append(f"at most PKR {high}")
    if cur.min_price is None and low is not None and prev.min_price == low:
        taken.append(f"at least PKR {low}")
    in_stock = cur.in_stock or prev.in_stock
    if in_stock and not cur.in_stock:
        taken.append("in stock")
    return replace(cur, colour=colour, terms=tuple(terms), min_price=low, max_price=high, in_stock=in_stock), taken


def with_history(history: Sequence[str], message: str, current: QueryIntent) -> tuple[QueryIntent, list[str]]:
    """(effective intent, what was kept from earlier messages). `current` is the already-parsed (and, for speech, bridged) message."""
    prev: QueryIntent | None = None
    for text in list(history)[-MAX_HISTORY:]:
        if not isinstance(text, str):
            continue
        intent = parse_query(text[:200])
        if intent.needs_review:
            continue
        prev = intent if prev is None else _carry(prev, intent, text)[0]
    if prev is None:
        return current, []
    return _carry(prev, current, message)
