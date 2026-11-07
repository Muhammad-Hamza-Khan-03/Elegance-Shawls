"""WhatsApp assistant: a model understands every message and writes every reply; code only grounds and checks it.

1. understand: the model reads the recent conversation plus a live stock summary and returns JSON: search, order, details, reply or handoff.
2. act: search runs the model's filters through the same hybrid catalogue search the website uses (a colour must exist in the live catalogue,
   prices are whole numbers); order shows a summary, then (only after the customer says yes) creates an enquiry through the website's
   validating code and links it to the chat; details saves name/city/address on it. Then the model writes the answer from those facts.
Products, prices, stock and links come only from the database (product cards are built here, never by the model), and a reply that
contains a link we did not produce is rejected. Prompts live in templates/assistant.yaml. Any gateway or parsing failure returns None,
and the caller sends the holding reply so a person follows up. Customer text is scrubbed (emails, URLs, phone numbers) and outside
development goes only through the gateway's no-training chain (LLM_PRODUCTION_CHAIN); with no chain configured the holding reply is sent.
"""
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from llm.gateway import get_gateway
from repositories import whatsapp as repo
from repositories.enquiries import Line, StaleCart, catalogue_snapshot, create_enquiry, stock_rows
from repositories.hybrid import embed_query, hybrid_search
from repositories.products import VariantFilter
from semantic.query_parser import MAX_PRICE
from semantic.representation import _SCRUB
from utils.colour_vocabulary import normalize
from whatsapp.matching import InboundEvent
from whatsapp.replies import FIELDS, _LIMITS as LIMITS, missing_fields

PROMPTS = Path(__file__).parent / "templates" / "assistant.yaml"
MAX_CARDS = 3
MAX_REPLY_CHARS = 1500
HISTORY_WINDOW = timedelta(hours=24)
DIGEST_TTL_SECONDS = 120
_URL = re.compile(r"https?://\S+")
_digest_cache: tuple[float, str, set[str]] | None = None


@lru_cache(maxsize=1)
def _prompts() -> dict:
    return yaml.safe_load(PROMPTS.read_text(encoding="utf-8"))


def _prompt(name: str, digest: str) -> str:
    p = _prompts()
    return p[name].replace("{shop}", p["shop"].strip()).replace("{digest}", digest)


async def _digest(session: AsyncSession) -> tuple[str, set[str]]:
    """What is in stock (types, colours, price range) read from the database, so the model never relies on a built-in list."""
    global _digest_cache
    if _digest_cache and time.monotonic() - _digest_cache[0] < DIGEST_TTL_SECONDS:
        return _digest_cache[1], _digest_cache[2]
    types: dict[str, set] = {}
    colours: dict[str, set] = {}
    ids, prices = set(), []
    for pid, category, colour, price, _stock in await stock_rows(session, None):
        ids.add(pid)
        prices.append(price)
        types.setdefault(str(getattr(category, "value", category)), set()).add(pid)
        if c := normalize(colour):
            colours.setdefault(c, set()).add(pid)
    count = lambda d: ", ".join(f"{k} {len(v)}" for k, v in sorted(d.items(), key=lambda kv: -len(kv[1])))  # noqa: E731
    text = (f"{len(ids)} products. Types: {count(types)}. Colours: {count(colours) or 'none recorded'}. Prices: PKR {min(prices):,} to {max(prices):,}."
            if ids else "Nothing is in stock right now.")
    _digest_cache = (time.monotonic(), text, set(colours))
    return text, set(colours)


def _clean(text: str, limit: int = 500) -> str:
    return " ".join(_SCRUB.sub(" ", text).split())[:limit]


def _buyable(v: dict) -> bool:
    return v["is_active"] is True and (v["stock"] or 0) > 0 and v["price"] is not None


def _variant(product: dict) -> dict | None:
    return next((v for v in product.get("variants", []) if _buyable(v)), None)


def _card(product: dict) -> str:
    v = _variant(product)
    link = f" {settings.whatsapp_site_url.rstrip('/')}/product/{product['slug']}" if settings.whatsapp_site_url and product.get("slug") else ""
    if v is None:
        return f"• {product['name']}: out of stock{link}"
    colour = f" ({v['color']})" if v.get("color") else ""
    return f"• {product['name']}{colour}: {v['currency']} {v['price']:,}{link}"


def _json(text: str) -> dict | None:
    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _whole(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_PRICE else None


def _transcript(turns: list[tuple[str, str]]) -> tuple[str, set[str]]:
    """The earlier conversation for the prompt and the links we ourselves sent in it (the only links a reply may repeat)."""
    lines, links = [], set()
    for who, text in turns:
        if who == "customer":
            lines.append(f"Customer: {_clean(text)}")
        else:
            links.update(_URL.findall(text))
            lines.append(f"{'Shop assistant' if who == 'bot' else 'Shop staff'}: {' '.join(text.split())[:600]}")
    return ("Conversation so far:\n" + "\n".join(lines) + "\n\n") if lines else "", links


def _safe(text, links: set[str]) -> str | None:
    """The model's reply as one plain message, or None when it is empty or carries a link we did not produce."""
    body = " ".join(str(text or "").split())[:MAX_REPLY_CHARS]
    return body if body and all(u.rstrip(".,)") in links for u in _URL.findall(body)) else None


async def _ask(system: str, user: str, personal: bool) -> str:
    """One gateway call. WHATSAPP_LLM_ALLOW_TRAINING=true is the operator's explicit choice to use the production chain as configured
    (training providers included); otherwise personal=True filters those out."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if settings.whatsapp_llm_allow_training:
        return (await get_gateway().complete(messages, logical="production", personal=False)).text
    return (await get_gateway().complete(messages, personal=personal)).text


def _filters(search: dict, colours: set[str]) -> tuple[VariantFilter | None, str, str | None]:
    """(hard filter, plain-English description of it, a requested colour that does not exist). Colour and prices are validated, never trusted."""
    wanted = " ".join(str(search.get("colour") or "").split())
    colour = normalize(wanted) if wanted else None
    lo, hi = _whole(search.get("min_price")), _whole(search.get("max_price"))
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    in_stock = search.get("in_stock") is True
    absent = wanted if wanted and colour not in colours else None
    colour = colour if colour in colours else None
    parts = [f"colour {colour}" if colour else "", f"at least PKR {lo}" if lo is not None else "", f"at most PKR {hi}" if hi is not None else "",
             "in stock" if in_stock else ""]
    flt = VariantFilter(colour, lo, hi, in_stock) if colour or lo is not None or hi is not None or in_stock else None
    return flt, ", ".join(p for p in parts if p) or "none", absent


def _facts(applied: str, absent: str | None, products: list[dict]) -> str:
    lines = [f"- {p['name']} ({p.get('category', 'item')}): "
             + (f"{v['currency']} {v['price']:,}" + (f", {v['color']}" if v.get("color") else "") if (v := _variant(p)) else "out of stock") for p in products]
    out = f"Filters applied (every product below satisfies them): {applied}.\n"
    if absent:
        out += f"The customer asked for colour '{absent}', which is not in stock in any product.\n"
    return out + ("Matching products (cards are attached):\n" + "\n".join(lines) if lines else "No product in the catalogue matched.")


async def _find(session: AsyncSession, q: str | None, flt: VariantFilter | None, limit: int) -> list[dict]:
    """Catalogue snapshots for a model-chosen search; the colour that was asked for is shown first, buyable products first."""
    page = await hybrid_search(session, q=q, limit=limit * 2, variant=flt, embedding=await embed_query(q) if q else None)
    snapshot = await catalogue_snapshot(session, [p.id for p in page.items])
    products = [snapshot[str(p.id)] for p in page.items if str(p.id) in snapshot]
    for p in products:
        p["variants"].sort(key=lambda v: (not _buyable(v), flt is None or not flt.colour or normalize(v.get("color")) != flt.colour))
    return sorted(products, key=lambda p: _variant(p) is None)[:limit]


def _item(qty: int, name: str, colour: str | None, currency: str, price: int) -> str:
    return f"• {qty} x {name}{f' ({colour})' if colour else ''}: {currency} {price:,}"


async def _order(session: AsyncSession, order: dict, colours: set[str], contact_id, now: datetime, has_summary: bool) -> tuple[str, list[str]]:
    """(facts, cards) for an order request. Nothing is created until the customer said yes to a summary we showed; prices and stock are re-read
    from the database and the enquiry goes through the same validating code as the website's checkout handoff."""
    chosen: dict[str, tuple[dict, dict, int]] = {}
    unresolved: list[str] = []
    for raw in (order.get("lines") if isinstance(order.get("lines"), list) else [])[:10]:
        if not isinstance(raw, dict):
            continue
        q = " ".join(_clean(str(raw.get("q") or ""), 100).split()[:6]) or None
        colour = normalize(str(raw.get("colour") or "")) if raw.get("colour") else None
        qty = raw.get("quantity") if _whole(raw.get("quantity")) and 1 <= raw["quantity"] <= 20 else 1
        found = [p for p in await _find(session, q, VariantFilter(colour if colour in colours else None, None, None, True), 3) if _variant(p)]
        named = [p for p in found if q and p["name"].casefold() == q.casefold()]
        pick = named[0] if len(named) == 1 else found[0] if len(found) == 1 else None
        if pick is None:
            unresolved.append(f"'{q or 'unspecified'}': " + (", ".join(p["name"] for p in found) or "nothing in stock matched"))
            continue
        v = _variant(pick)
        old = chosen.get(v["id"], (pick, v, 0))[2]
        chosen[v["id"]] = (pick, v, min(old + qty, v["stock"]))
    if unresolved or not chosen:
        return "Could not identify these items, ask which one they mean: " + "; ".join(unresolved or ["no product named"]), []
    lines = list(chosen.values())
    if len({v["currency"] for _, v, _ in lines}) > 1:
        return "These items are priced in different currencies; a team member will arrange this order.", []
    currency, total = lines[0][1]["currency"], sum(v["price"] * q for _, v, q in lines)
    cards = [_item(q, p["name"], v.get("color"), v["currency"], v["price"]) for p, v, q in lines] + [f"Total: {currency} {total:,}"]
    if not (order.get("confirmed") is True and has_summary):
        return "Order summary shown below; nothing is placed yet. Ask the customer to reply yes to place the order.", cards
    signature = sorted((str(p["id"]), v["id"], q) for p, v, q in lines)
    enquiry = await repo.open_enquiry_for_contact(session, contact_id)
    if enquiry is None or sorted((i["product_id"], i["variant_id"], i["quantity"]) for i in enquiry.items) != signature:   # same cart again: reuse, never duplicate
        try:
            enquiry = await create_enquiry(session, [Line(uuid.UUID(str(p["id"])), uuid.UUID(v["id"]), q, v["price"], v["currency"]) for p, v, q in lines])
        except StaleCart:
            return "Prices or stock changed while ordering; nothing was placed. Say so and offer to show the current options.", []
        await repo.link_enquiry(session, enquiry, contact_id, "reference", now)
    missing = missing_fields(enquiry.customer_details or {})
    return (f"Order enquiry placed: reference {enquiry.reference}, total {currency} {total:,} (items below). It is not confirmed: the team confirms availability, "
            f"delivery and payment. Delivery details still missing: {', '.join(missing) or 'none'}."), cards


async def _details(session: AsyncSession, given: dict, contact_id) -> str | None:
    enquiry = await repo.open_enquiry_for_contact(session, contact_id)
    if enquiry is None:
        return None
    new = {k: " ".join(str(given.get(k) or "").split())[:LIMITS[k]] for k in FIELDS}
    new = {k: v for k, v in new.items() if v}
    merged = {**(enquiry.customer_details or {}), **new}
    enquiry.customer_details = merged                          # a new dict, so the JSON column registers the change
    return (f"Saved delivery details for enquiry {enquiry.reference}: {', '.join(new) or 'nothing new'}. "
            f"Still missing: {', '.join(missing_fields(merged)) or 'nothing; all details are in'}. The team will confirm availability, delivery and payment.")


async def answer(session: AsyncSession, event: InboundEvent, contact_id, now: datetime) -> str | None:
    """The reply text, or None when the assistant has nothing safe to say (the caller then sends the holding reply)."""
    text = (event.text or "").strip()
    if not text:
        return None
    personal = settings.environment != "development"
    turns = await repo.recent_turns(session, contact_id, event.wa_id, now - HISTORY_WINDOW)
    transcript, links = _transcript(turns)
    digest, colours = await _digest(session)
    enquiry = await repo.open_enquiry_for_contact(session, contact_id)
    state = (f"Open order enquiry {enquiry.reference}: " + "; ".join(f"{i['quantity']} x {i['product']}" for i in enquiry.items)
             + f". Delivery details still missing: {', '.join(missing_fields(enquiry.customer_details or {})) or 'none'}.\n\n") if enquiry else ""
    message = f"{transcript}{state}NEW MESSAGE ({'voice transcript' if event.type == 'audio' else 'typed'}):\n{_clean(text)}"
    plan = _json(await _ask(_prompt("understand", digest), message, personal))
    if not plan:
        return None
    action = plan.get("action")
    sub = lambda key: plan.get(key) if isinstance(plan.get(key), dict) else {}  # noqa: E731
    cards: list[str] = []
    if action == "reply":
        return _safe(plan.get("reply"), links)
    if action == "search":
        search = sub("search")
        q = " ".join(_clean(str(search.get("q") or ""), 100).split()[:6]) or None
        flt, applied, absent = _filters(search, colours)
        products = [] if absent else await _find(session, q, flt, MAX_CARDS)
        cards = [_card(p) for p in products]
        facts = _facts(applied, absent, products)
    elif action == "order":
        facts, cards = await _order(session, sub("order"), colours, contact_id, now, any(who == "bot" for who, _ in turns))
    elif action == "details":
        facts = await _details(session, sub("details"), contact_id)
        if facts is None:
            return None
    else:
        return None                                          # handoff (or anything unrecognised): a person answers
    reply = _safe(await _ask(_prompt("respond", digest), f"{transcript}{state}Facts:\n{facts}\n\nNEW MESSAGE:\n{_clean(text)}", personal),
                  links | {u for c in cards for u in _URL.findall(c)})
    return "\n".join([reply, *cards])[:MAX_REPLY_CHARS] if reply else None
