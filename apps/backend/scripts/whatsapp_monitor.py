"""Prometheus text metrics and alert check for the WhatsApp bridge (run from apps/backend; needs DATABASE_URL, REDIS_URL, bridge env).

  python scripts/whatsapp_monitor.py            # print metrics (Prometheus text) for a textfile collector / Grafana agent
  python scripts/whatsapp_monitor.py --check    # print firing alerts, exit 2 if any (cron / uptime monitor)
Disabled bridge: prints nothing and exits 0.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redis.asyncio import Redis  # noqa: E402

from configuration.config import settings  # noqa: E402
from database.pg import close_postgres, connect_to_postgres, session_factory  # noqa: E402
from whatsapp import config as wa_config, monitoring  # noqa: E402


async def main(check: bool) -> int:
    if not wa_config.is_enabled():
        return 0
    await connect_to_postgres()
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3) if settings.redis_url else None
    try:
        async with session_factory()() as session:
            snap = await monitoring.collect(session, redis)
    finally:
        if redis is not None:
            await redis.aclose()
        await close_postgres()
    if check:
        for alert in snap.alerts:
            print(f"ALERT {alert}")
        return 2 if snap.alerts else 0
    print(monitoring.prometheus(snap), end="")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--check" in sys.argv)))
