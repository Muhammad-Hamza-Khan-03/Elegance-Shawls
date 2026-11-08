"""Customer photo -> closest buyable products with real pgvector. The embedder is a stub: this proves the pipeline and its rules
(threshold, stock, one row per product, photo discarded), not CLIP's visual quality."""
import hashlib
from datetime import datetime, timezone

import pytest

from configuration.config import settings
from repositories import image_match as repo
from search.image_match import DIMENSION, ImageMatchError
from tests.integration.api_support import H, ApiEnv
from tests.integration.test_api_products import payload, variant
from whatsapp.image_service import MATCHED, match_event
from whatsapp.matching import InboundEvent


def vec(*pairs):
    v = [0.0] * DIMENSION
    for i, x in pairs:
        v[i] = x
    return v


class Stub:
    model = "clip-ViT-B-32"

    def __init__(self, vector=None, boom=False):
        self.vector, self.boom = vector, boom

    def embed_image(self, data):
        if self.boom:
            raise ImageMatchError("image could not be embedded")
        return self.vector


class Client:
    def __init__(self):
        self.deleted = []

    async def fetch_media(self, media_id):
        return b"JPEG", "image/jpeg"

    async def delete_media(self, media_id):
        self.deleted.append(media_id)


@pytest.fixture
def env(pg_engine_factory, migrated_url, monkeypatch):
    e = ApiEnv(migrated_url, monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_bridge_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_bridge_token", "t")
    monkeypatch.setattr(settings, "redis_url", "redis://x")
    monkeypatch.setattr(settings, "whatsapp_image_enabled", True)
    monkeypatch.setattr(settings, "image_match_model_path", "/models/clip")
    monkeypatch.setattr(settings, "whatsapp_site_url", "https://shop.example")
    # (slug, name, colour, stock, vector): the photo will look like index 0
    shapes = [("teal-shawl", "Teal Shawl", "Teal", 3, vec((0, 1.0))), ("near-shawl", "Teal Stole", "Teal", 2, vec((0, 0.9), (1, 0.4))),
              ("sold-out", "Teal Wrap", "Teal", 0, vec((0, 1.0))), ("red-shawl", "Red Shawl", "Red", 5, vec((2, 1.0)))]
    variant_ids = {}
    for slug, name, colour, stock, v in shapes:
        body = {**payload(slug), "name": name, "status": "active", "variants": [variant(name, color=colour, price=3500, stock=stock)]}
        created = e.client.post("/products/admin/", json=body, headers=H).json()
        variant_ids[slug] = (created["variants"][0]["_id"], v)

    async def seed(sessions):
        import uuid
        async with sessions() as session, session.begin():
            for variant_id, v in variant_ids.values():
                await repo.upsert(session, uuid.UUID(variant_id), "clip-ViT-B-32", hashlib.sha256(variant_id.encode()).hexdigest(), v)
    e.run(seed)
    return e


def photo_event(**over):
    base = dict(v=1, wa_id="IMG1", chat="923001234567@s.whatsapp.net", from_me=False, type="image", media="image:IMG1", ts=datetime(2026, 11, 7, tzinfo=timezone.utc))
    return InboundEvent(**{**base, **over})


def run(env, event, embedder, client):
    async def work(sessions):
        return await match_event(event, client, sessions, embedder)
    return env.run(work)


def test_the_closest_buyable_products_are_returned_and_the_photo_is_discarded(env):
    client = Client()
    event, reply = run(env, photo_event(), Stub(vec((0, 1.0))), client)
    assert event.media == MATCHED and client.deleted == ["IMG1"]
    lines = [l for l in reply.splitlines() if l.startswith("•")]
    assert lines[0].startswith("• Teal Shawl (Teal): PKR 3,500 https://shop.example/product/teal-shawl")
    assert any("Teal Stole" in l for l in lines)                 # similar enough (cosine ~0.91)
    assert not any("Teal Wrap" in l for l in lines)              # sold out: never offered
    assert not any("Red Shawl" in l for l in lines)              # orthogonal: below the threshold
    assert "Order on WhatsApp" in reply


def test_nothing_close_says_so_instead_of_guessing(env):
    _, reply = run(env, photo_event(), Stub(vec((100, 1.0))), Client())
    assert "could not find a close match" in reply and "•" not in reply


def test_a_failing_model_leaves_a_plain_image_and_still_deletes_the_photo(env):
    client = Client()
    event, reply = run(env, photo_event(), Stub(boom=True), client)
    assert reply is None and event.media is None and client.deleted == ["IMG1"]


def test_other_events_and_a_disabled_switch_are_left_alone(env, monkeypatch):
    client = Client()
    for e in (photo_event(from_me=True), photo_event(media=None), photo_event(type="audio")):
        assert run(env, e, Stub(vec((0, 1.0))), client) == (e, None)
    assert client.deleted == []
    monkeypatch.setattr(settings, "whatsapp_image_enabled", False)
    event, reply = run(env, photo_event(), Stub(vec((0, 1.0))), client)
    assert reply is None and event.media is None and client.deleted == ["IMG1"]       # held by the bridge but not processed: discarded
