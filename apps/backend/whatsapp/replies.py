"""Automated replies: a pure state machine (no I/O) plus template rendering. The consumer decides; the bridge only delivers.

Replies are fixed templates filled from database facts, never model text. The bot never states an order is confirmed.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

TEMPLATES = Path(__file__).parent / "templates" / "replies.yaml"
FIELDS = ("name", "city", "address")
_LABELS = {"name": "name|نام", "city": "city|شہر", "address": "address|پتہ"}
_DETAIL_RE = re.compile(rf"^\s*({'|'.join(_LABELS.values())})\s*[:：\-]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_KEY = {alias: key for key, aliases in _LABELS.items() for alias in aliases.split("|")}
_LIMITS = {"name": 100, "city": 80, "address": 300}


@dataclass(frozen=True)
class Facts:
    now: datetime
    event_ts: datetime
    text: str | None
    max_age: timedelta
    allowlisted: bool
    paused: bool                      # staff typed in this chat within the pause window
    bot_recent: bool                  # the bot already wrote to this chat within the pause window
    reference_in_message: bool
    has_enquiry: bool                 # an open enquiry is linked to this chat
    summary_sent: bool
    details: dict = field(default_factory=dict)
    issues: tuple = ()                # live-catalogue problems for the enquiry's items (see repositories.whatsapp.verify_items)
    unknown_reference: bool = False   # the message carries a reference that matches no open enquiry of this chat
    assistant_enabled: bool = False   # WHATSAPP_ASSISTANT_ENABLED: free text goes to the catalogue assistant, not a holding reply
    is_text: bool = False             # there is text to answer (typed, or a transcribed voice note)


@dataclass(frozen=True)
class Decision:
    kind: str                         # summary | changed | ask_missing | details_done | need_reference | holding | assistant
    save_details: dict | None = None
    flag: str | None = None           # staff-visible marker written to enquiries.customer_details["staff_flag"]
    missing: tuple = ()


def parse_details(text: str | None) -> dict:
    found = {}
    for label, value in _DETAIL_RE.findall(text or ""):
        key = _KEY.get(label.lower())
        if key and key not in found:
            found[key] = value[:_LIMITS[key]]
    return found


def missing_fields(details: dict) -> tuple:
    return tuple(f for f in FIELDS if not details.get(f))


def decide(f: Facts) -> Decision | None:
    if not f.allowlisted or f.paused or f.now - f.event_ts > f.max_age:
        return None
    holding = Decision("assistant") if f.assistant_enabled and f.is_text else None if f.bot_recent else Decision("holding")
    if not f.has_enquiry:
        if f.assistant_enabled and f.is_text and not f.unknown_reference:
            return Decision("assistant")
        return None if f.bot_recent else Decision("need_reference")
    if not f.summary_sent:
        if not f.reference_in_message:
            return holding
        if f.issues:
            return Decision("changed", flag="price_or_stock_changed")
        return Decision("summary", missing=missing_fields(f.details))
    new = parse_details(f.text)
    if not new:
        return holding
    merged = {**f.details, **new}
    still = missing_fields(merged)
    if still:
        return Decision("ask_missing", save_details=new, missing=still)
    return Decision("details_done", save_details=new) if missing_fields(f.details) else None


@lru_cache(maxsize=1)
def _templates() -> dict:
    return yaml.safe_load(TEMPLATES.read_text(encoding="utf-8"))


def language(text: str | None) -> str:
    return "ur" if re.search(r"[؀-ۿ]", text or "") else "en"


def _money(amount: int, currency: str) -> str:
    return f"{currency} {amount:,}"


def _item_name(item: dict) -> str:
    variant = " / ".join(x for x in (item.get("color"), item.get("size")) if x)
    return f"{item['product']} ({variant})" if variant else item["product"]


def render(decision: Decision, *, lang: str, reference: str, items: list, total: int, currency: str, issues: tuple = ()) -> str:
    t = _templates()[lang]
    fields = "\n".join(t[f"field_{m}"] for m in decision.missing)
    if decision.kind == "summary":
        lines = "\n".join(f"{i}. {_item_name(it)} x {it['quantity']} = {_money(it['unit_price'] * it['quantity'], currency)}" for i, it in enumerate(items, 1))
        ask = t["ask_details"].format(fields=fields) if decision.missing else ""
        return t["summary"].format(reference=reference, lines=lines, total=_money(total, currency), ask=ask).strip()
    if decision.kind == "changed":
        by_variant = {it["variant_id"]: it for it in items}
        changes = "\n".join(t[f"change_{i['reason']}"].format(item=_item_name(by_variant[i["variant_id"]]), available=i.get("available"),
                            price=_money(i["current_price"], i.get("current_currency", currency)) if "current_price" in i else "")
                            for i in issues if i["variant_id"] in by_variant)
        return t["changed"].format(reference=reference, changes=changes).strip()
    if decision.kind == "ask_missing":
        return t["ask_missing"].format(fields=fields)
    return t[decision.kind]
