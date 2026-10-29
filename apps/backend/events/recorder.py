"""Best-effort server-side event recording. Failures are logged and swallowed, never raised."""
import logging

from fastapi import Request

from configuration.config import settings
from database.pg import open_session
from events.session import verify_session_token
from models.relational_model import Event

logger = logging.getLogger("elegance.events")
MAX_LISTED_IDS = 20


def opted_out(request: Request) -> bool:
    """Honour Do Not Track and Global Privacy Control on the server as well as in the tracker."""
    return request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1"


async def record_server_event(event_type: str, payload: dict, session_id: str | None) -> None:
    if not settings.session_signing_key:
        return  # events are disabled until a signing key is configured
    try:
        session = open_session()
        if session is None:
            return
        async with session:
            session.add_all([Event(session_id=session_id or "unattributed", type=event_type, payload=payload)])
            await session.commit()
    except Exception as exc:
        logger.warning("server event not recorded: %s", type(exc).__name__)


async def log_listing(request: Request, *, limit: int, paged: bool, product_ids: list[str]) -> None:
    """Impression of the public listing with result positions.

    The listing has no server-side query or filters (search is client-side today), so only limit and
    paging are recorded. Query text and parsed filters are logged by the PostgreSQL-backed search
    endpoint in Phase 1, where server-side search actually exists.
    """
    if opted_out(request):
        return
    token = request.headers.get("x-session-token") or request.cookies.get("es_sid")
    await record_server_event(
        "impression",
        {"surface": "listing", "limit": limit, "paged": paged, "returned": len(product_ids),
         "product_ids": ",".join(product_ids[:MAX_LISTED_IDS])},
        verify_session_token(token),
    )
