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
    return None
