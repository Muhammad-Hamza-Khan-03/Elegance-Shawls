import asyncio
import uuid
from datetime import timedelta

import pytest

from repositories import Conflict, InvalidDraft, NotFound
from repositories import products as repo
from repositories.products import VariantInput
from tests.integration.repo_helpers import count, product_input, run_repo, tx


# ---- create ----------------------------------------------------------------------------------
def test_create_draft_product_with_ordered_variants(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input(variants=[
                VariantInput(name="A", image_url="u", price=3000, stock=1),
                VariantInput(name="B", image_url="u", price=2500, stock=0, color="Black"),
            ]))
        async with sessions() as s:
            loaded = await repo.get_product(s, created.id)
            return (loaded.status, loaded.is_active, loaded.revision, loaded.price, loaded.images, loaded.currency,
                    [(v.name, v.position, v.stock_status) for v in loaded.variants], isinstance(loaded.id, uuid.UUID))

    assert run_repo(pg_engine_factory, scenario) == (
        "draft", False, 1, 2500, ["https://img.example/c.jpg"], "PKR",
        [("A", 0, "In stock"), ("B", 1, "Out of stock")], True)


def test_cover_image_is_listed_first_and_explicit_price_wins(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input(images=["https://img.example/2.jpg"], price=9000))
        return created.images, created.price

    assert run_repo(pg_engine_factory, scenario) == (["https://img.example/c.jpg", "https://img.example/2.jpg"], 9000)


def test_duplicate_slug_conflicts_without_poisoning_the_transaction(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            await repo.create_product(s, product_input("taken"))
        async with tx(sessions) as s:
            with pytest.raises(Conflict):
                await repo.create_product(s, product_input("taken", name="Other"))
            await repo.create_product(s, product_input("free"))        # the same transaction is still usable
        return await count(sessions, "products"), await count(sessions, "variants")

    assert run_repo(pg_engine_factory, scenario) == (2, 2)


@pytest.mark.parametrize("over", [{"price": -1}, {"slug": "Bad Slug"}, {"category": "hats"}, {"status": "live"}])
def test_invalid_product_is_rejected_and_nothing_is_saved(pg_engine_factory, over):
    async def scenario(sessions):
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.create_product(s, product_input(**over))
        return await count(sessions, "products")

    assert run_repo(pg_engine_factory, scenario) == 0


def test_a_product_needs_a_variant(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.create_product(s, repo.ProductInput(slug="x", name="X", cover_image_url="u", variants=[]))

    run_repo(pg_engine_factory, scenario)


def test_repository_never_commits_so_callers_can_roll_back(pg_engine_factory):
    async def scenario(sessions):
        async with sessions() as s:
            await repo.create_product(s, product_input("uncommitted"))
            async with sessions() as other:                       # a second connection cannot see it yet
                assert await repo.get_public_product_by_slug(other, "uncommitted") is None
                assert await count(sessions, "products") == 0
            await s.rollback()
        return await count(sessions, "products")

    assert run_repo(pg_engine_factory, scenario) == 0


# ---- reads -----------------------------------------------------------------------------------
def test_public_reads_only_see_active_products(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            for slug, status in (("live", "active"), ("hidden", "draft"), ("gone", "archived"), ("out", "out_of_stock")):
                await repo.create_product(s, product_input(slug, status=status))
        async with sessions() as s:
            public = await repo.list_products(s, public=True, limit=10)
            admin = await repo.list_products(s, public=False, limit=10)
            return (sorted(p.slug for p in public.items), sorted(p.slug for p in admin.items),
                    (await repo.get_public_product_by_slug(s, "LIVE")).slug,       # slug lookup is case-insensitive
                    [await repo.get_public_product_by_slug(s, x) for x in ("hidden", "gone", "out", "missing")])

    assert run_repo(pg_engine_factory, scenario) == (["live"], ["gone", "hidden", "live", "out"], "live", [None] * 4)


def test_get_product_by_uuid_and_unknown_uuid(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input())
        async with sessions() as s:
            return (await repo.get_product(s, created.id)).slug, await repo.get_product(s, uuid.uuid4())

    assert run_repo(pg_engine_factory, scenario) == ("classic-pashmina", None)


def test_keyset_pagination_visits_every_product_exactly_once(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:                              # ONE transaction => identical created_at for all rows
            for i in range(7):
                await repo.create_product(s, product_input(f"p-{i}", status="active"))
        seen, after, pages = [], None, 0
        async with sessions() as s:
            while True:
                page = await repo.list_products(s, public=True, limit=3, after=after)
                seen += [p.slug for p in page.items]
                pages += 1
                if page.next_after is None:
                    break
                after = page.next_after
        return pages, len(seen), len(set(seen))

    assert run_repo(pg_engine_factory, scenario) == (3, 7, 7)     # 3 + 3 + 1, no duplicates, no gaps despite equal timestamps


def test_pagination_is_newest_first_and_stable_when_new_rows_arrive(pg_engine_factory):
    async def scenario(sessions):
        for i in range(4):
            async with tx(sessions) as s:                          # separate transactions => distinct timestamps
                await repo.create_product(s, product_input(f"n-{i}", status="active"))
        async with sessions() as s:
            first = await repo.list_products(s, public=True, limit=2)
        async with tx(sessions) as s:                              # a newer product appears between page requests
            await repo.create_product(s, product_input("newest", status="active"))
        async with sessions() as s:
            second = await repo.list_products(s, public=True, limit=2, after=first.next_after)
        return [p.slug for p in first.items], [p.slug for p in second.items]

    assert run_repo(pg_engine_factory, scenario) == (["n-3", "n-2"], ["n-1", "n-0"])


# ---- lifecycle ---------------------------------------------------------------------------------
def test_publish_unpublish_archive_maintain_revision_and_updated_at(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input())
        steps = [("publish", repo.publish_product, "active", True), ("unpublish", repo.unpublish_product, "draft", False),
                 ("archive", repo.archive_product, "archived", False)]
        seen, previous = [], created
        for name, fn, status, active in steps:
            async with tx(sessions) as s:
                changed = await fn(s, created.id)
            seen.append((status, changed.status, changed.is_active, changed.revision, changed.updated_at > previous.updated_at))
            previous = changed
        return seen

    assert run_repo(pg_engine_factory, scenario) == [
        ("active", "active", True, 2, True), ("draft", "draft", False, 3, True), ("archived", "archived", False, 4, True)]


def test_status_changes_on_unknown_products_are_not_found(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            for fn in (repo.publish_product, repo.unpublish_product, repo.archive_product):
                with pytest.raises(NotFound):
                    await fn(s, uuid.uuid4())

    run_repo(pg_engine_factory, scenario)


def test_create_does_not_publish_unless_asked(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            await repo.create_product(s, product_input())
        return await count(sessions, "products", "is_active")

    assert run_repo(pg_engine_factory, scenario) == 0


# ---- stock -------------------------------------------------------------------------------------
def test_stock_update_changes_status_label_and_bumps_revision(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input())
        variant_id = created.variants[0].id
        async with tx(sessions) as s:
            out = await repo.set_variant_stock(s, created.id, variant_id, 0)
        async with tx(sessions) as s:
            back = await repo.set_variant_stock(s, created.id, variant_id, 7)
        return (out.variants[0].stock, out.variants[0].stock_status, out.revision,
                back.variants[0].stock, back.variants[0].stock_status, back.revision)

    assert run_repo(pg_engine_factory, scenario) == (0, "Out of stock", 2, 7, "In stock", 3)


def test_stock_update_rejects_negative_and_foreign_variants(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            one = await repo.create_product(s, product_input("one"))
            two = await repo.create_product(s, product_input("two"))
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.set_variant_stock(s, one.id, one.variants[0].id, -1)
            with pytest.raises(NotFound):                         # a variant of ANOTHER product
                await repo.set_variant_stock(s, one.id, two.variants[0].id, 5)
            with pytest.raises(NotFound):
                await repo.set_variant_stock(s, uuid.uuid4(), one.variants[0].id, 5)
        async with sessions() as s:
            return (await repo.get_product(s, one.id)).variants[0].stock, (await repo.get_product(s, two.id)).variants[0].stock

    assert run_repo(pg_engine_factory, scenario) == (4, 4)


def test_concurrent_stock_updates_are_serialised_and_both_counted(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input())
        variant_id = created.variants[0].id

        async def update(value):
            async with tx(sessions) as s:
                await repo.set_variant_stock(s, created.id, variant_id, value)

        await asyncio.gather(*(update(v) for v in range(10, 20)))
        async with sessions() as s:
            final = await repo.get_product(s, created.id)
            return final.variants[0].stock in range(10, 20), final.revision

    assert run_repo(pg_engine_factory, scenario) == (True, 11)    # one of the writes won, and every write bumped the revision


# ---- replace (PUT) -----------------------------------------------------------------------------
def test_replace_keeps_known_variants_adds_new_and_removes_omitted(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input(variants=[
                VariantInput(name="A", image_url="u", price=100, stock=1), VariantInput(name="B", image_url="u", price=100, stock=2),
                VariantInput(name="C", image_url="u", price=100, stock=3)]))
        a, b, c = (v.id for v in created.variants)
        async with tx(sessions) as s:
            replaced = await repo.replace_product(s, created.id, product_input(
                name="Renamed", price=500, variants=[
                    VariantInput(id=c, name="C!", image_url="u", price=500, stock=9),       # kept, moved first
                    VariantInput(name="New", image_url="u", price=500, stock=1),            # new
                    VariantInput(id=uuid.uuid4(), name="Stranger", image_url="u", price=500),   # unknown id => treated as new
                ]))
        ids = [v.id for v in replaced.variants]
        return (replaced.name, replaced.revision, [v.name for v in replaced.variants], ids[0] == c,
                a not in ids and b not in ids, len(set(ids)), [v.position for v in replaced.variants],
                await count(sessions, "variants"))

    assert run_repo(pg_engine_factory, scenario) == ("Renamed", 2, ["C!", "New", "Stranger"], True, True, 3, [0, 1, 2], 3)


def test_replace_conflict_and_missing_product_leave_everything_unchanged(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            one = await repo.create_product(s, product_input("one"))
            await repo.create_product(s, product_input("two"))
        async with tx(sessions) as s:
            with pytest.raises(Conflict):
                await repo.replace_product(s, one.id, product_input("two", name="Hijack"))
            with pytest.raises(NotFound):
                await repo.replace_product(s, uuid.uuid4(), product_input("zzz"))
        async with sessions() as s:
            unchanged = await repo.get_product(s, one.id)
            return unchanged.slug, unchanged.name, unchanged.revision, len(unchanged.variants)

    assert run_repo(pg_engine_factory, scenario) == ("one", "Classic Pashmina", 1, 1)


def test_a_failed_replace_rolls_back_variant_changes(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input())
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):                      # negative price violates a CHECK mid-replace
                await repo.replace_product(s, created.id, product_input(variants=[
                    VariantInput(name="X", image_url="u", price=-5)]))
        async with sessions() as s:
            kept = await repo.get_product(s, created.id)
            return [v.name for v in kept.variants], kept.revision

    assert run_repo(pg_engine_factory, scenario) == (["Burgundy"], 1)


def test_replace_cannot_activate_an_ingested_product_that_is_not_published(pg_engine_factory):
    from models.relational_model import StagedProduct
    from tests.integration.repo_helpers import NOW

    async def scenario(sessions):
        async with tx(sessions) as s:
            created = await repo.create_product(s, product_input())
            s.add(StagedProduct(source_id="p", source_name="P", source_url="https://s/1", source_content_hash="h",
                                dedupe_key="id:1", fetched_at=NOW, normalized_at=NOW, product={}, status="approved",
                                product_id=created.id, approved_price=1, stock_known=True))
        async with tx(sessions) as s:
            with pytest.raises(Conflict):
                await repo.replace_product(s, created.id, product_input(status="active"))
            with pytest.raises(Conflict):
                await repo.publish_product(s, created.id)
            await repo.replace_product(s, created.id, product_input(status="draft", name="Still draft"))   # other edits are fine
            return True

    assert run_repo(pg_engine_factory, scenario)
