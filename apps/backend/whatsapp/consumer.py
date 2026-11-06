"""`python -m whatsapp.consumer`: reads Redis Stream `wa:inbound` (group `backend`) into PostgreSQL.

Acks only after the transaction commits; an entry that fails MAX_ATTEMPTS times moves to `wa:dead`. Disabled => logs once, exits 0.
shortcut: attempt counts live in memory (a restart grants fresh attempts), upgrade to XPENDING delivery counts if poison messages recur.
"""
import asyncio
import json
import logging
import signal
import sys

from pydantic import ValidationError

from configuration.config import settings
from whatsapp import config as wa_config
from whatsapp.ingest import ingest
from whatsapp.matching import InboundEvent
from whatsapp.reply_service import BridgeSender, SendRefused, maybe_reply

logger = logging.getLogger("whatsapp.consumer")
STREAM, GROUP, DEAD = "wa:inbound", "backend", "wa:dead"
MAX_ATTEMPTS = 5


async def handle_entry(sessions, redis, entry_id, fields, attempts: dict, sender=None) -> None:
    try:
        event = InboundEvent.model_validate_json(fields[b"event"] if b"event" in fields else fields["event"])
        async with sessions() as session, session.begin():
            await ingest(session, event)
        if sender is not None:
            await maybe_reply(sessions, event, sender)
    except SendRefused as exc:
        logger.warning("bridge refused reply for %s: %s", entry_id, exc)     # permanent: record nothing more, ack below
    except Exception as exc:
        attempts[entry_id] = attempts.get(entry_id, 0) + 1
        permanent = isinstance(exc, (ValidationError, KeyError))
        if not permanent and attempts[entry_id] < MAX_ATTEMPTS:
            logger.warning("entry %s failed (attempt %d): %s", entry_id, attempts[entry_id], exc)
            return                                   # stays pending; re-read on the next pass
        logger.error("entry %s dead-lettered: %s", entry_id, exc)
        await redis.xadd(DEAD, {"entry": str(entry_id), "error": str(exc)[:500], "fields": json.dumps({str(k): str(v)[:2000] for k, v in fields.items()})})
    attempts.pop(entry_id, None)
    await redis.xack(STREAM, GROUP, entry_id)


async def run(stop: asyncio.Event) -> None:
    from redis.asyncio import Redis
    from redis.exceptions import ResponseError
    from database.pg import connect_to_postgres, session_factory, close_postgres

    await connect_to_postgres()
    redis = Redis.from_url(settings.redis_url)      # no socket timeout: XREADGROUP blocks
    try:
        await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    sessions, attempts, pending, sender = session_factory(), {}, True, BridgeSender()
    try:
        while not stop.is_set():
            # "0" re-reads this consumer's unacked entries (retries after a crash); ">" reads new ones.
            reply = await redis.xreadgroup(GROUP, "consumer-1", {STREAM: "0" if pending else ">"}, count=50, block=None if pending else 2000)
            entries = reply[0][1] if reply else []
            if pending and not entries:
                pending = False
                continue
            for entry_id, fields in entries:
                await handle_entry(sessions, redis, entry_id, fields, attempts, sender)
            if attempts:
                pending = True                       # a failed entry stays unacked: go back and retry it
                await asyncio.sleep(1)               # ...without hot-looping
    finally:
        await redis.aclose()
        await close_postgres()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if not wa_config.is_enabled():
        logger.info("WHATSAPP_BRIDGE_ENABLED is false; consumer not started")
        return 0
    if problem := wa_config.misconfiguration():
        logger.error("WhatsApp consumer cannot start: %s", problem)
        return 1

    async def go():
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        await run(stop)

    asyncio.run(go())
    return 0


if __name__ == "__main__":
    sys.exit(main())
