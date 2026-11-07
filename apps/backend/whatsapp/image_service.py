"""Customer photo -> closest in-stock catalogue products, fully local. The photo is fetched once from the bridge's in-memory holder,
embedded by the local CLIP model, matched with pgvector, and deleted; only the reply text is kept (media_ref marks the message as
image_matched). Any failure leaves a plain image message, which gets the "could not read it, please type" reply.
"""
import logging

from configuration.config import settings
from repositories import image_match as repo
from search import image_match
from whatsapp import config as wa_config
from whatsapp.matching import InboundEvent
from whatsapp.replies import _templates, language

logger = logging.getLogger("whatsapp.image")
MATCHED = "image_matched"


def render(matches: list, lang: str = "en") -> str:
    t = _templates()[lang]
    if not matches:
        return t["image_none"]
    link = settings.whatsapp_site_url.rstrip("/")
    lines = [f"• {m.name}{f' ({m.colour})' if m.colour else ''}: {m.currency} {m.price:,}" + (f" {link}/product/{m.slug}" if link and m.slug else "") for m in matches]
    return "\n".join([t["image_intro"], *lines, t["assistant_footer"]])


async def match_event(event: InboundEvent, client, sessions, embedder=None) -> tuple[InboundEvent, str | None]:
    handle = event.media or ""
    if event.type != "image" or event.from_me or not handle.startswith("image:"):
        return event, None
    media_id = handle.removeprefix("image:")
    try:
        if not wa_config.image_ready():
            return event.model_copy(update={"media": None}), None
        embedder = embedder or image_match.get_embedder()
        data, _ = await client.fetch_media(media_id)
        vector = embedder.embed_image(data)
        async with sessions() as session:
            matches = await repo.nearest(session, vector, embedder.model, settings.image_match_max_results, settings.image_match_min_similarity)
        return event.model_copy(update={"media": MATCHED}), render(matches, language(event.text))
    except Exception as exc:
        logger.warning("photo not matched: %s", type(exc).__name__)
        return event.model_copy(update={"media": None}), None
    finally:
        try:
            await client.delete_media(media_id)
        except Exception:
            pass                                       # the bridge also drops it after a few minutes
