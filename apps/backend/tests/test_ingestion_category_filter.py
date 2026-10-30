"""Category allowlist in run_job: stubs the page fetch and staging, so no network, provider or database."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio

from configuration.config import settings
from ingestion import pipeline
from ingestion.normalize import InvalidSourceData
from ingestion.safe_fetch import SourcePolicy
from tests.fixtures.ingestion import scraped_products as fx

POLICY = SourcePolicy("shop.example", True)


@pytest.fixture
def run(monkeypatch):
    calls = {"fetch": 0, "extract": 0, "staged": 0}

    async def fake_page(fetcher, url):
        calls["fetch"] += 1
        return {"source_url": url, "html": "<p>x</p>", "raw_html": "<p>x</p>", "images": fx.PEARL["image_urls"]}

    async def fake_stage(sessions, normalized, **kw):
        calls["staged"] += 1
        return SimpleNamespace(id=uuid4()), "created"

    monkeypatch.setattr(pipeline, "fetch_product_page_clean_html", fake_page)
    monkeypatch.setattr(pipeline, "stage_product", fake_stage)

    async def go(category, allowed):
        monkeypatch.setattr(settings, "ingestion_allowed_categories", allowed)

        class Extractor:
            async def extract(self, **kw):
                calls["extract"] += 1
                return {**fx.PEARL, "category": category}

        job = SimpleNamespace(id=uuid4(), path="/products/pearl-cashmere-shawl", source_id="primary")
        return await pipeline.run_job(None, job, fetcher=SimpleNamespace(policy=POLICY), extractor=Extractor())

    go.calls = calls
    return go


@pytest.mark.parametrize("category", ["shawl", "stole"])
async def test_allowed_categories_are_staged(run, category):
    assert (await run(category, "shawl, Stole"))["outcome"] == "created"
    assert run.calls["staged"] == 1


@pytest.mark.parametrize("category", ["scarf", "accessory"])
async def test_other_categories_are_rejected_without_staging(run, category):
    with pytest.raises(InvalidSourceData):
        await run(category, "shawl,stole")
    assert run.calls["staged"] == 0 and run.calls["fetch"] == 1  # only the existing source fetch


async def test_unset_allowlist_keeps_current_behaviour(run):
    assert (await run("scarf", ""))["outcome"] == "created"
