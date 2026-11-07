"""Embed catalogue variant images with the LOCAL CLIP model (run from apps/backend; needs DATABASE_URL, IMAGE_MATCH_MODEL_PATH/REVISION).

  python scripts/image_embedding_backfill.py [--limit 100] [--after <variant uuid>]

Resumable and idempotent: an unchanged image (same SHA-256) is skipped. Only https images on the ingestion image allowlist
(INGESTION_SOURCE_DOMAIN / INGESTION_IMAGE_HOSTS) are fetched, to a public address, following at most 3 redirects that are each re-checked, capped at 5 MB.
shortcut: the connection is not pinned to the validated address (SafeFetcher pins pages, not images); pin it if the allowlist ever widens.
"""
import argparse
import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from database.pg import close_postgres, connect_to_postgres, session_factory  # noqa: E402
from ingestion.safe_fetch import SourcePolicy, is_allowed_image_url, resolve_public, system_resolver  # noqa: E402
from models.relational_model import Variant  # noqa: E402
from repositories import image_match as repo  # noqa: E402
from search.image_match import MAX_IMAGE_BYTES, ImageMatchError, get_embedder  # noqa: E402


async def fetch_image(client: httpx.AsyncClient, url: str, policy: SourcePolicy, max_hops: int = 3) -> bytes | None:
    """Every hop (including redirects) must be https on the image allowlist and resolve to a public address."""
    current = url
    for _ in range(max_hops + 1):
        if not is_allowed_image_url(current, policy):
            return None
        await resolve_public(httpx.URL(current).host, system_resolver)
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                current = str(httpx.URL(current).join(response.headers["location"]))
                continue
            if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_IMAGE_BYTES:
                    return None
            return bytes(body)
    return None


async def main(limit: int, after: str | None) -> int:
    embedder = get_embedder()
    if embedder is None:
        print("IMAGE_MATCH_MODEL_PATH is not set", file=sys.stderr)
        return 2
    policy = SourcePolicy.from_settings()
    await connect_to_postgres()
    done = skipped = failed = 0
    last = None
    try:
        async with session_factory()() as session, httpx.AsyncClient(timeout=15.0) as client:
            stmt = select(Variant.id, Variant.image_url).where(Variant.is_active.is_(True)).order_by(Variant.id).limit(limit)
            if after:
                stmt = stmt.where(Variant.id > uuid.UUID(after))
            for variant_id, url in (await session.execute(stmt)).all():
                last = variant_id
                try:
                    data = await fetch_image(client, url, policy)
                    if data is None:
                        failed += 1
                        continue
                    digest = hashlib.sha256(data).hexdigest()
                    if await repo.existing_hash(session, variant_id, embedder.model) == digest:
                        skipped += 1
                        continue
                    await repo.upsert(session, variant_id, embedder.model, digest, embedder.embed_image(data))
                    await session.commit()
                    done += 1
                except Exception as exc:   # one bad image must not stop the run
                    await session.rollback()
                    failed += 1
                    print(f"variant {variant_id}: {type(exc).__name__}", file=sys.stderr)
    finally:
        await close_postgres()
    print({"embedded": done, "skipped": skipped, "failed": failed, "last_id": str(last) if last else None})
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.limit, args.after)))
