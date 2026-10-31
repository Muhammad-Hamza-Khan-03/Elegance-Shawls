"""arq job for enrichment. It never raises (so arq cannot add retries beyond the contract) and writes only suggestions."""
import logging
import uuid

from enrichment import service
from workers.jobs import traced

logger = logging.getLogger("elegance.worker")


@traced
async def run_enrichment_job(ctx: dict, suggestion_id: str) -> dict:
    sessions = ctx.get("pg_sessions")
    if sessions is None:
        return {"skipped": "postgres is not configured"}
    try:
        return {"status": await service.process(sessions, uuid.UUID(suggestion_id))}
    except Exception as exc:  # an unexpected bug must not trigger an arq redelivery and a second provider call
        logger.error("enrichment job crashed: %s", type(exc).__name__)
        return {"status": "error", "error": type(exc).__name__}
