import asyncio
from datetime import datetime, timezone

import pytest

from configuration.config import settings
from whatsapp import config as wa_config
from whatsapp.matching import InboundEvent
from whatsapp.voice_service import TRANSCRIBED, transcribe_event


class Client:
    def __init__(self):
        self.deleted = []

    async def fetch_media(self, media_id):
        return b"OggS", "audio/ogg; codecs=opus"

    async def delete_media(self, media_id):
        self.deleted.append(media_id)


def voice(**over):
    base = dict(v=1, wa_id="V1", chat="923001234567@s.whatsapp.net", from_me=False, type="audio", media="voice:V1", ts=datetime(2026, 11, 6, tzinfo=timezone.utc))
    return InboundEvent(**{**base, **over})


@pytest.fixture
def ready(monkeypatch):
    for k, v in dict(whatsapp_bridge_enabled=True, whatsapp_bridge_token="t", redis_url="redis://x", whatsapp_voice_enabled=True,
                     whatsapp_asr_url="http://asr/v1/audio/transcriptions", whatsapp_asr_privacy="self_hosted").items():
        monkeypatch.setattr(settings, k, v)


async def fake_asr(audio, mimetype):
    assert audio == b"OggS"
    return "red shawl under 3000"


def test_voice_is_transcribed_then_the_audio_is_dropped(ready):
    client = Client()
    out = asyncio.run(transcribe_event(voice(), client, fake_asr))
    assert out.text == "red shawl under 3000" and out.media == TRANSCRIBED and client.deleted == ["V1"]


def test_asr_failure_keeps_a_plain_audio_message_and_still_deletes(ready):
    async def boom(audio, mimetype):
        raise RuntimeError("down")
    client = Client()
    out = asyncio.run(transcribe_event(voice(), client, boom))
    assert out.text is None and out.media is None and client.deleted == ["V1"]


def test_not_ready_without_a_declared_privacy_class(ready, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_asr_privacy", "may_train")
    assert not wa_config.voice_ready() and "WHATSAPP_ASR_PRIVACY" in wa_config.misconfiguration()
    client = Client()
    out = asyncio.run(transcribe_event(voice(), client, fake_asr))
    assert out.text is None and client.deleted == ["V1"]       # never sent to the ASR


def test_other_events_pass_through_untouched(ready):
    client = Client()
    for e in (voice(from_me=True), voice(media=None), voice(type="text", text="hi", media=None)):
        assert asyncio.run(transcribe_event(e, client, fake_asr)) is e
    assert client.deleted == []
