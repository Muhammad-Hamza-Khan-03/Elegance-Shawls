"""Health metrics and alert rules for the WhatsApp bridge. `evaluate` is pure; `collect` gathers the facts (no writes).

Rules (plan "Monitoring"): not connected for >10 min while enabled, needs_pairing immediately, consumer lag >500 on wa:inbound,
non-empty wa:dead. Rendered as Prometheus text for a Grafana Cloud agent / textfile collector (scripts/whatsapp_monitor.py).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from models.relational_model import Enquiry, WhatsAppMessage
from whatsapp import config as wa_config

DISCONNECTED_AFTER = timedelta(minutes=10)
LAG_LIMIT = 500


@dataclass(frozen=True)
class Snapshot:
    now: datetime
    state: str                                   # bridge state, or misconfigured / unreachable
    state_since: datetime | None = None
    lag: int | None = None                       # None = unknown (no Redis from here)
    dead: int | None = None
    ingested_last_hour: int = 0
    linked_by_reference: int = 0
    linked_by_staff: int = 0
    median_contact_seconds: float | None = None
    alerts: list = field(default_factory=list)


def evaluate(s: Snapshot) -> list[str]:
    alerts = []
    if s.state == "needs_pairing":
        alerts.append("needs_pairing: the linked device was logged out; pair again from Admin > WhatsApp")
    elif s.state != "connected":
        since = s.state_since
        if since is None or s.now - since > DISCONNECTED_AFTER:
            alerts.append(f"disconnected: bridge state is '{s.state}' (more than 10 minutes, or unknown since when)")
    if s.lag is not None and s.lag > LAG_LIMIT:
        alerts.append(f"consumer_lag: {s.lag} entries waiting on wa:inbound (limit {LAG_LIMIT})")
    if s.dead:
        alerts.append(f"dead_letters: {s.dead} entries in wa:dead")
    return alerts


def prometheus(s: Snapshot) -> str:
    rows = [
        ("whatsapp_bridge_connected", 1 if s.state == "connected" else 0),
        ("whatsapp_consumer_lag", s.lag), ("whatsapp_dead_letters", s.dead),
        ("whatsapp_messages_ingested_last_hour", s.ingested_last_hour),
        ('whatsapp_enquiries_linked{source="reference"}', s.linked_by_reference),
        ('whatsapp_enquiries_linked{source="staff"}', s.linked_by_staff),
        ("whatsapp_handoff_to_contacted_median_seconds", s.median_contact_seconds),
        ("whatsapp_alerts_firing", len(s.alerts)),
    ]
    return "".join(f"{name} {value}\n" for name, value in rows if value is not None)


async def _bridge() -> tuple[str, datetime | None]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            reply = await client.get(f"{settings.whatsapp_bridge_url}/health", headers={"Authorization": f"Bearer {settings.whatsapp_bridge_token}"})
            reply.raise_for_status()
            body = reply.json()
        since = body.get("state_since")
        return body.get("state", "unreachable"), datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
    except (httpx.HTTPError, ValueError):
        return "unreachable", None


async def _streams(redis) -> tuple[int | None, int | None]:
    if redis is None:
        return None, None
    try:
        groups = {g["name"]: g for g in await redis.xinfo_groups("wa:inbound")}
        lag = groups.get("backend", {}).get("lag")
        return lag, await redis.xlen("wa:dead")
    except Exception:
        return None, None


async def collect(session: AsyncSession, redis, now: datetime | None = None) -> Snapshot:
    now = now or datetime.now(timezone.utc)
    problem = wa_config.misconfiguration()
    state, since = ("misconfigured", None) if problem else await _bridge()
    lag, dead = await _streams(redis)
    ingested = (await session.execute(select(func.count()).select_from(WhatsAppMessage)
                                      .where(WhatsAppMessage.received_at > now - timedelta(hours=1)))).scalar_one()
    by_source = dict((await session.execute(select(Enquiry.link_source, func.count()).where(Enquiry.link_source.is_not(None)).group_by(Enquiry.link_source))).all())
    # Time from handoff (enquiry created) to the first staff message in the linked chat.
    median = (await session.execute(text(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (first_staff - created_at))) FROM ("
        " SELECT e.created_at, (SELECT min(m.sent_at) FROM whatsapp_messages m WHERE m.enquiry_id = e.id AND m.sent_by = 'staff') AS first_staff"
        " FROM enquiries e WHERE e.status IN ('contacted','converted','lost')) t WHERE first_staff IS NOT NULL"))).scalar_one()
    snap = Snapshot(now=now, state=state, state_since=since, lag=lag, dead=dead, ingested_last_hour=ingested,
                    linked_by_reference=by_source.get("reference", 0), linked_by_staff=by_source.get("staff", 0),
                    median_contact_seconds=float(median) if median is not None else None)
    return Snapshot(**{**snap.__dict__, "alerts": evaluate(snap) if wa_config.is_enabled() else []})
