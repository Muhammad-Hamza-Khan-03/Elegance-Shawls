"""Voice notes -> text before ingestion. Raw audio is fetched once from the bridge's in-memory holder, transcribed by the
declared self-hosted / no-training ASR, and deleted; only the transcript is stored (media_ref marks it as transcribed).
Any failure leaves the event as a plain audio message: the customer gets the holding reply and staff listen on the phone.
"""
import logging

from voice import asr
from whatsapp import config as wa_config
from whatsapp.matching import InboundEvent

logger = logging.getLogger("whatsapp.voice")
TRANSCRIBED = "voice_transcribed"


async def transcribe_event(event: InboundEvent, client, transcribe=asr.transcribe) -> InboundEvent:
    media_id = (event.media or "").removeprefix("voice:") if (event.media or "").startswith("voice:") else None
    if event.type != "audio" or event.from_me or not media_id:
        return event
    if not wa_config.voice_ready():
        await _drop(client, media_id)                 # held by the bridge but we may not process it: discard now
        return event.model_copy(update={"media": None})
    try:
        audio, mimetype = await client.fetch_media(media_id)
        text = await transcribe(audio, mimetype)
        return event.model_copy(update={"text": text, "media": TRANSCRIBED})
    except Exception as exc:
        logger.warning("voice note not transcribed: %s", type(exc).__name__)
        return event.model_copy(update={"media": None})
    finally:
        await _drop(client, media_id)


async def _drop(client, media_id: str) -> None:
    try:
        await client.delete_media(media_id)
    except Exception:
        pass                                          # the bridge also drops it after a few minutes
