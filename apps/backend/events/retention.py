"""Retention for interaction events (18 months by default). Run it from cron or a one-shot job:
`python -m events.retention`. shortcut: not scheduled anywhere yet; schedule it with the ops
workstream and add the customer-facing retention wording to the privacy copy backlog."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import make_engine
from models.relational_model import Event


async def purge_expired_events(session: AsyncSession, months: int | None = None, now: datetime | None = None) -> int:
    months = settings.events_retention_months if months is None else months
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=30 * months)
    result = await session.execute(delete(Event).where(Event.created_at < cutoff))
    await session.commit()
    return result.rowcount or 0


async def _main() -> None:
    engine = make_engine()
    async with AsyncSession(engine) as session:
        print(f"purged {await purge_expired_events(session)} events")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
