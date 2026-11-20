"""Audio retention for voice jobs (issue #111). Clears the clip reference of jobs older than the retention window and
keeps the row as a metric. Run from cron or a one-shot job: `python -m voice.retention`.
shortcut: not scheduled anywhere yet and the clip store itself is not built, so this only forgets the reference; schedule it with
the ops workstream and delete the stored object by `audio_ref` once a store exists."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import make_engine
from models.relational_model import VoiceJob

DEFAULT_RETENTION_HOURS = 24


async def expire_voice_audio(session: AsyncSession, hours: int = DEFAULT_RETENTION_HOURS, now: datetime | None = None) -> int:
    moment = now or datetime.now(timezone.utc)
    result = await session.execute(
        update(VoiceJob)
        .where(VoiceJob.audio_ref.is_not(None), VoiceJob.created_at < moment - timedelta(hours=hours))
        .values(audio_ref=None, audio_deleted_at=moment)
    )
    await session.commit()
    return result.rowcount or 0


async def _main() -> None:
    engine = make_engine()
    async with AsyncSession(engine) as session:
        print(f"expired audio for {await expire_voice_audio(session)} voice jobs")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
