from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from models.relational_model import VoiceJob
from voice.retention import expire_voice_audio

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


async def _add(db, **kw):
    async with db.sessions() as s:
        job = VoiceJob(session_id="s1", duration_ms=kw.pop("duration_ms", 5000), **kw)
        s.add(job)
        await s.commit()


@pytest.mark.asyncio
async def test_clip_longer_than_30_seconds_is_rejected_by_the_database(db):
    with pytest.raises(IntegrityError):
        await _add(db, duration_ms=30001)


@pytest.mark.asyncio
async def test_expiry_clears_only_old_audio_and_keeps_the_row(db):
    await _add(db, audio_ref="clip-old", created_at=NOW - timedelta(hours=25))
    await _add(db, audio_ref="clip-new", created_at=NOW - timedelta(hours=1))
    async with db.sessions() as s:
        assert await expire_voice_audio(s, hours=24, now=NOW) == 1
    async with db.sessions() as s:
        rows = {r.created_at: r for r in (await s.execute(VoiceJob.__table__.select())).all()}
    old, new = rows[NOW - timedelta(hours=25)], rows[NOW - timedelta(hours=1)]
    assert old.audio_ref is None and old.audio_deleted_at == NOW
    assert new.audio_ref == "clip-new" and new.audio_deleted_at is None
    async with db.sessions() as s:
        assert await expire_voice_audio(s, hours=24, now=NOW) == 0  # idempotent
