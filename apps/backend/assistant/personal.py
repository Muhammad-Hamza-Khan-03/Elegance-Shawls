"""Saved memory in the assistant. Deterministic, consent-first, and never inferred.

* Reading: only for a signed-in customer who opted in (memory.service). Two keys are used: favourite_colour and budget_max_pkr.
  They only re-order results already found (a preferred colour or a budget under the limit first); they are never a hard filter.
* Writing: the assistant never saves anything. When the customer says "remember ..." / "yaad rakho ...", or states a taste ("I like
  pink", "mujhe kala pasand hai"), it offers the value it parsed as a Save card and the customer presses Save in the UI (the memory
  API then applies the usual consent, validation and audit). A taste is only offered once the customer has opted in.
* Recall: "what do I like?" is answered from the customer's own saved items, deterministically, without a model.
* Models: saved values reach an LLM only when memory.policy.authorize_model_use clears the whole personal-data chain.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from memory import service
from memory.policy import authorize_model_use
from semantic.query_parser import parse_query
from utils.colour_vocabulary import normalize

KEYS = ("favourite_colour", "budget_max_pkr", "preferred_category")
CATEGORIES = {"shawl": "shawls", "shawls": "shawls", "stole": "stoles", "stoles": "stoles", "scarf": "scarves", "scarfs": "scarves", "scarves": "scarves"}
_REMEMBER = re.compile(r"\b(remember|yaad\s*(?:rakh\w*|kar\w*)|save\s+(?:this|that|my|it))\b|یاد\s*رکھ", re.IGNORECASE)


_RECALL = re.compile(r"\b(what\s+do\s+i\s+(like|prefer)|what\s+(have\s+you|did\s+you)\s+(saved?|remember)|what\s+do\s+you\s+remember|my\s+(fav\w*|preferences?|saved)|"
                     r"mujhe\s+kya\s+pasand|mer[ei]\s+pasand|kya\s+yaad|mera\s+pasandida)\b", re.IGNORECASE)
_TASTE = re.compile(r"\b(i\s+(really\s+)?(like|love|prefer|adore)|my\s+favou?rite\s+is|pasand|prefer)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Preferences:
    state: str                      # "anonymous" | "off" | "on"
    values: dict[str, str]          # the keys the assistant understands (KEYS)
    everything: tuple[tuple[str, str], ...] = ()   # all of this customer's own live items, for recall only

    @property
    def category(self) -> str | None:
        return self.values.get("preferred_category") if self.values.get("preferred_category") in set(CATEGORIES.values()) else None

    @property
    def colour(self) -> str | None:
        return normalize(self.values["favourite_colour"]) if "favourite_colour" in self.values else None

    @property
    def budget(self) -> int | None:
        raw = self.values.get("budget_max_pkr", "")
        return int(raw) if raw.isdigit() and int(raw) > 0 else None


async def load(session, principal) -> Preferences:
    if principal is None:
        return Preferences("anonymous", {})
    try:
        items = await service.list_items(session, principal.customer_id, datetime.now(timezone.utc))
    except service.MemoryRejected:
        return Preferences("off", {})
    return Preferences("on", {i.key: i.value for i in items if i.key in KEYS}, tuple((i.key, i.value) for i in items))


def _extract(message: str) -> list[dict]:
    intent = parse_query(message)
    found = []
    if intent.colour:
        found.append({"key": "favourite_colour", "value": intent.colour})
    if intent.max_price is not None:
        found.append({"key": "budget_max_pkr", "value": str(intent.max_price)})
    category = next((CATEGORIES[t] for t in intent.terms if t in CATEGORIES), None)
    if category:
        found.append({"key": "preferred_category", "value": category})
    return found


def remember_request(message: str) -> list[dict] | None:
    """None when the message is not an explicit remember request; else the values to propose (possibly none)."""
    return _extract(message) if _REMEMBER.search(message) else None


def is_recall(message: str) -> bool:
    return bool(_RECALL.search(message))


def taste_offer(message: str, prefs: "Preferences") -> list[dict]:
    """Values worth offering to save after a statement of taste ("I like pink"); never the ones already saved. Offer only, never save."""
    if prefs.state != "on" or not _TASTE.search(message):
        return []
    return [o for o in _extract(message) if prefs.values.get(o["key"]) != o["value"]]


def recall_text(prefs: "Preferences") -> str:
    if prefs.state == "anonymous":
        return "I can only remember things for you once you sign in on the Account page and turn memory on. "
    if prefs.state == "off":
        return "Memory is off, so I have nothing saved. Turn it on in Account, then Manage memory. "
    if not prefs.everything:
        return "You have not saved anything yet. Say for example: remember I like pink, and I will offer to save it. "
    listed = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in prefs.everything[:10])
    return f"Here is what you saved: {listed}. You can change or delete these on the memory page. "


def rank(products: list[dict], prefs: Preferences, colour_in_query: bool) -> tuple[list[dict], list[str]]:
    """Stable re-order by saved preference; returns (products, labels of the preferences that were applied)."""
    colour, budget, category = (None if colour_in_query else prefs.colour), prefs.budget, prefs.category

    def key(p):
        live = [v for v in p["variants"] if v["is_active"] is True and (v["stock"] or 0) > 0]
        has_colour = colour is None or any(normalize(v.get("color") or "") == colour for v in live)
        in_budget = budget is None or any(v["price"] is not None and v["price"] <= budget for v in live)
        return (not has_colour, not in_budget, category is not None and p.get("category") != category)

    ordered = sorted(products, key=key)
    applied = ([f"favourite colour {colour}"] if colour else []) + ([f"budget up to PKR {budget}"] if budget else []) + (
        [f"preferred category {category}"] if category else [])
    return ordered, applied


def llm_allowed(models) -> bool:
    """May saved memory be put in a prompt for these models? (consent is already established by load())"""
    return authorize_model_use(True, models).allowed
