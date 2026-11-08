from configuration.config import settings


def is_enabled() -> bool:
    return settings.whatsapp_bridge_enabled


def misconfiguration() -> str | None:
    """Why an enabled bridge cannot run, or None. A disabled bridge is never 'misconfigured'."""
    if not is_enabled():
        return None
    if not settings.whatsapp_bridge_token:
        return "WHATSAPP_BRIDGE_TOKEN is not set"
    if not settings.redis_url:
        return "REDIS_URL is not set"
    if settings.whatsapp_voice_enabled and not (settings.whatsapp_asr_url and settings.whatsapp_asr_privacy in ASR_PRIVACY):
        return "WHATSAPP_VOICE_ENABLED needs WHATSAPP_ASR_URL and WHATSAPP_ASR_PRIVACY=self_hosted|no_training"
    if settings.whatsapp_image_enabled and not settings.image_match_model_path:
        return "WHATSAPP_IMAGE_ENABLED needs IMAGE_MATCH_MODEL_PATH (a local CLIP model directory)"
    return None


ASR_PRIVACY = ("self_hosted", "no_training")


def voice_ready() -> bool:
    """Voice notes are transcribed only with a declared self-hosted / no-training ASR endpoint (plan 19.2)."""
    return is_enabled() and settings.whatsapp_voice_enabled and bool(settings.whatsapp_asr_url) and settings.whatsapp_asr_privacy in ASR_PRIVACY


def image_ready() -> bool:
    """Photo matching runs only with a local model directory: customer photos are never sent to a hosted model."""
    return is_enabled() and settings.whatsapp_image_enabled and bool(settings.image_match_model_path)
