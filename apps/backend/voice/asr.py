"""Speech-to-text over an OpenAI-compatible `/audio/transcriptions` endpoint (e.g. a self-hosted faster-whisper server).

The endpoint's privacy class is declared by the operator (WHATSAPP_ASR_PRIVACY) and checked by whatsapp.config.voice_ready;
audio is passed through in memory and never stored here.
"""
import httpx

from configuration.config import settings

MAX_TRANSCRIPT_CHARS = 2000


class AsrError(Exception):
    pass


async def transcribe(audio: bytes, mimetype: str = "audio/ogg") -> str:
    headers = {"Authorization": f"Bearer {settings.whatsapp_asr_api_key}"} if settings.whatsapp_asr_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            reply = await client.post(settings.whatsapp_asr_url, headers=headers, data={"model": settings.whatsapp_asr_model, "response_format": "json"},
                                      files={"file": ("voice.ogg", audio, mimetype.split(";")[0])})
        reply.raise_for_status()
        text = str(reply.json().get("text", "")).strip()
    except (httpx.HTTPError, ValueError) as exc:
        raise AsrError(f"transcription failed: {type(exc).__name__}") from exc
    if not text:
        raise AsrError("empty transcript")
    return text[:MAX_TRANSCRIPT_CHARS]
