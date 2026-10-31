"""Catalogue-grounded assistant: parse the message, search the live catalogue, propose only what the kernel will validate.

No model is called: the M2-S4 parser turns words into hard filters, hybrid_search (lexical unless an embedder is wired) finds
products, and every card/price/revision comes from catalogue_snapshot, never from message text. An ambiguous query gets a
clarifying question instead of a guess. Nothing executes here; the user must still confirm (routes/action_routes.py).
"""
import hashlib
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from actions import kernel as k
from configuration.config import settings
from database.pg import get_pg_session
from repositories.enquiries import catalogue_snapshot
from repositories.hybrid import hybrid_search
from semantic.query_parser import handoff, parse_query

MAX_CARDS = 3


def _key(base: str, n: int) -> str:
    return "idem_" + hashlib.sha256(f"{base}:{n}".encode()).hexdigest()[:24]


def _buyable(product: dict) -> dict | None:
    return next((v for v in product["variants"] if v["is_active"] is True and (v["stock"] or 0) > 0 and v["price"] is not None), None)


async def catalogue_session():
    """A DB session only when the assistant is grounded in the live catalogue; the scripted demo needs none."""
    if not settings.assistant_catalogue:
        yield None
        return
    async for session in get_pg_session():
        yield session


async def _say(*lines: str) -> AsyncIterator[dict]:
    for line in lines:
        yield {"type": "text", "delta": line}


async def _cards(products: list[dict], idempotency_key: str) -> AsyncIterator[dict]:
    yield {"type": "text", "delta": f"I found {len(products)} that match. "}
    for product in products:
        yield {"type": "product", "product_id": product["id"]}
    top, variant = products[0], _buyable(products[0])
    if variant:
        yield {"type": "proposal", "action_type": "add_to_cart", "idempotency_key": _key(idempotency_key, 1),
               "params": {"product_id": top["id"], "variant_id": variant["id"], "quantity": 1, "expected_revision": top["revision"],
                          "expected_unit_price": variant["price"], "currency": variant["currency"]}}
        yield {"type": "text", "delta": "Say the word and I will add the first one to your cart."}


async def ground(session: AsyncSession, message: str, idempotency_key: str) -> tuple[AsyncIterator[dict], k.InMemoryCatalogue]:
    intent = parse_query(message)
    plan = handoff(intent)
    if plan is None:
        asks = tuple(f"{q} " for q in intent.clarifications) or ("Could you tell me a little more about what you are looking for?",)
        return _say(*asks), k.InMemoryCatalogue({})
    page = await hybrid_search(session, q=plan.q, limit=MAX_CARDS, variant=plan.variant)
    snapshot = await catalogue_snapshot(session, [p.id for p in page.items])
    products = [snapshot[str(p.id)] for p in page.items if str(p.id) in snapshot]
    if not products:
        return _say("I could not find a match right now. Try a different colour or budget, or browse the full collection."), k.InMemoryCatalogue({})
    return _cards(products, idempotency_key), k.InMemoryCatalogue(snapshot)
