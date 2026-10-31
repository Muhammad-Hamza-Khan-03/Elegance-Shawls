"""Saved memory in the assistant. Deterministic, consent-first, and never inferred.

* Reading: only for a signed-in customer who opted in (memory.service). Two keys are used: favourite_colour and budget_max_pkr.
  They only re-order results already found (a preferred colour or a budget under the limit first); they are never a hard filter.
* Writing: the assistant never saves anything. When the customer explicitly says "remember ..." / "yaad rakho ...", it proposes the
  value it parsed and the customer presses Save in the UI (the memory API then applies the usual consent, validation and audit).
* Models: saved values reach an LLM only when memory.policy.authorize_model_use clears the whole personal-data chain.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from memory import service
from memory.policy import authorize_model_use
from semantic.query_parser import parse_query
from utils.colour_vocabulary import normalize

KEYS = ("favourite_colour", "budget_max_pkr")
LABEL = {"favourite_colour": "favourite colour", "budget_max_pkr": "budget (PKR, at most)"}
# Explicit only: a statement of taste on its own ("I like brown") is never saved or suggested for saving.
_REMEMBER = re.compile(r"\b(remember|yaad\s*(?:rakh\w*|kar\w*)|save\s+(?:this|that|my|it))\b|یاد\s*رکھ", re.IGNORECASE)


@dataclass(frozen=True)
class Preferences:
    state: str                      # "anonymous" | "off" | "on"
    values: dict[str, str]

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
    return Preferences("on", {i.key: i.value for i in items if i.key in KEYS})


def remember_request(message: str) -> list[dict] | None:
    """None when the message is not an explicit remember request; else the values to propose (possibly none)."""
    if not _REMEMBER.search(message):
        return None
    intent = parse_query(message)
    found = []
    if intent.colour:
        found.append({"key": "favourite_colour", "value": intent.colour})
    if intent.max_price is not None:
        found.append({"key": "budget_max_pkr", "value": str(intent.max_price)})
    return found


def rank(products: list[dict], prefs: Preferences, colour_in_query: bool) -> tuple[list[dict], list[str]]:
    """Stable re-order by saved preference; returns (products, labels of the preferences that were applied)."""
    colour, budget = (None if colour_in_query else prefs.colour), prefs.budget

    def key(p):
        live = [v for v in p["variants"] if v["is_active"] is True and (v["stock"] or 0) > 0]
        has_colour = colour is None or any(normalize(v.get("color") or "") == colour for v in live)
        in_budget = budget is None or any(v["price"] is not None and v["price"] <= budget for v in live)
        return (not has_colour, not in_budget)

    ordered = sorted(products, key=key)
    applied = ([f"favourite colour {colour}"] if colour else []) + ([f"budget up to PKR {budget}"] if budget else [])
    return ordered, applied


def llm_allowed(models) -> bool:
    """May saved memory be put in a prompt for these models? (consent is already established by load())"""
    return authorize_model_use(True, models).allowed
