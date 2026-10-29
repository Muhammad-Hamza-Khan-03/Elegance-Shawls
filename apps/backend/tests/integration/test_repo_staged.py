import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.relational_model import StagedProductAudit
from repositories import Conflict, InvalidDraft, InvalidTransition, NotFound, ProductUnavailable
from repositories import products as catalogue
from repositories import staged as repo
from repositories.products import VariantInput
from schemas.ingestion_schema import StagedStatus as S
from tests.integration.repo_helpers import NOW, count, draft, product_input, run_repo, stage_kwargs, tx


async def stage(sessions, n=1, **over):
    async with tx(sessions) as s:
        row, outcome = await repo.stage_product(s, **stage_kwargs(n, **over))
    return row, outcome


async def trail(sessions, staged_id):
    async with sessions() as s:
        return [(a.action, a.from_status, a.to_status, a.actor) for a in (await repo.get_staged(s, staged_id)).audit]


# ---- staging with dedupe -----------------------------------------------------------------------
def test_stage_creates_a_pending_review_row_with_an_audit_entry(pg_engine_factory):
    async def scenario(sessions):
        row, outcome = await stage(sessions, 1)
        return (outcome, row.status, row.stock_known, row.dedupe_key, row.missing_fields, float(row.source_price),
                row.product["slug"], await trail(sessions, row.id))

    assert run_repo(pg_engine_factory, scenario) == (
        "created", "pending_review", False, "id:1", ["price", "stock"], 29.5, "staged-1",
        [("staged", None, "pending_review", "ingestion")])


def test_dedupe_key_falls_back_to_the_url_when_the_source_has_no_id(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1, source_product_id=None)
        return row.dedupe_key

    assert run_repo(pg_engine_factory, scenario) == "url:https://source.example/p/1"


def test_restaging_identical_content_is_unchanged(pg_engine_factory):
    async def scenario(sessions):
        first, _ = await stage(sessions, 1)
        again, outcome = await stage(sessions, 1)
        return outcome, again.id == first.id, await count(sessions, "staged_products"), len(await trail(sessions, first.id))

    assert run_repo(pg_engine_factory, scenario) == ("unchanged", True, 1, 1)


def test_restaging_changed_content_updates_a_row_still_in_review(pg_engine_factory):
    async def scenario(sessions):
        first, _ = await stage(sessions, 1)
        updated, outcome = await stage(sessions, 1, source_content_hash="hash-new", source_price=31, product=draft("renamed"))
        return (outcome, updated.id == first.id, updated.source_content_hash, updated.product["slug"],
                float(updated.source_price), [a[0] for a in await trail(sessions, first.id)])

    assert run_repo(pg_engine_factory, scenario) == ("updated", True, "hash-new", "renamed", 31.0, ["staged", "source_updated"])


def test_a_reviewed_row_is_never_overwritten_only_flagged(pg_engine_factory):
    async def scenario(sessions):
        first, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            await repo.approve(s, first.id, price=4500, stock=3)
        flagged, outcome = await stage(sessions, 1, source_content_hash="hash-new", product=draft("hostile-rewrite"))
        async with sessions() as s:
            product = await catalogue.get_product(s, flagged.product_id)
        return (outcome, flagged.status, flagged.source_content_hash, flagged.latest_source_hash, flagged.product["slug"],
                product.slug, [(a[0]) for a in await trail(sessions, first.id)])

    assert run_repo(pg_engine_factory, scenario) == (
        "source_changed", "approved", "hash-1", "hash-new", "staged-1", "staged-1", ["staged", "approve", "source_changed"])


def test_concurrent_stagers_of_the_same_item_produce_one_row_and_one_created(pg_engine_factory):
    async def scenario(sessions):
        async def go():
            async with tx(sessions) as s:
                return (await repo.stage_product(s, **stage_kwargs(1)))[1]

        outcomes = await asyncio.gather(*(go() for _ in range(6)))
        return sorted(outcomes), await count(sessions, "staged_products"), await count(sessions, "staged_product_audit")

    assert run_repo(pg_engine_factory, scenario) == (["created"] + ["unchanged"] * 5, 1, 1)


def test_the_same_key_from_a_different_source_is_a_different_item(pg_engine_factory):
    async def scenario(sessions):
        await stage(sessions, 1)
        await stage(sessions, 1, source_id="second")
        return await count(sessions, "staged_products")

    assert run_repo(pg_engine_factory, scenario) == 2


# ---- listing ----------------------------------------------------------------------------------
def test_list_by_status_and_keyset_pagination(pg_engine_factory):
    async def scenario(sessions):
        ids = []
        for n in range(5):
            row, _ = await stage(sessions, n)
            ids.append(row.id)
        async with tx(sessions) as s:
            await repo.reject(s, ids[0], "Not our style")
        async with sessions() as s:
            pending = await repo.list_staged(s, status="pending_review", limit=10)
            rejected = await repo.list_staged(s, status="rejected", limit=10)
            seen, after = [], None
            while True:
                page = await repo.list_staged(s, status=None, limit=2, after=after)
                seen += [r.id for r in page.items]
                after = page.next_after
                if after is None:
                    break
            return len(pending.items), len(rejected.items), len(seen), len(set(seen))

    assert run_repo(pg_engine_factory, scenario) == (4, 1, 5, 5)


# ---- transitions are compare-and-set --------------------------------------------------------
@pytest.mark.parametrize("target", [S.PUBLISHED, S.UNPUBLISHED])
def test_illegal_transitions_are_refused_and_change_nothing(pg_engine_factory, target):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            with pytest.raises(InvalidTransition) as error:
                await repo.transition(s, row.id, target, "force")
        async with sessions() as s:
            return error.value.current, (await repo.get_staged(s, row.id)).status, len(await trail(sessions, row.id))

    assert run_repo(pg_engine_factory, scenario) == ("pending_review", "pending_review", 1)


def test_transition_on_a_missing_staged_product_is_not_found(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            with pytest.raises(NotFound):
                await repo.transition(s, uuid.uuid4(), S.REJECTED, "reject")

    run_repo(pg_engine_factory, scenario)


def test_concurrent_approvals_create_exactly_one_product(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)

        async def approve():
            async with tx(sessions) as s:
                try:
                    await repo.approve(s, row.id, price=4500, stock=2)
                    return "approved"
                except InvalidTransition:
                    return "refused"

        outcomes = await asyncio.gather(*(approve() for _ in range(5)))
        return sorted(outcomes), await count(sessions, "products"), await count(sessions, "variants"), \
            [a[0] for a in await trail(sessions, row.id)]

    assert run_repo(pg_engine_factory, scenario) == (["approved"] + ["refused"] * 4, 1, 2, ["staged", "approve"])


def test_concurrent_approve_and_reject_have_exactly_one_winner(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)

        async def act(kind):
            async with tx(sessions) as s:
                try:
                    if kind == "approve":
                        await repo.approve(s, row.id, price=100)
                    else:
                        await repo.reject(s, row.id, "Wrong category")
                    return kind
                except InvalidTransition:
                    return None

        winners = [w for w in await asyncio.gather(act("approve"), act("reject")) if w]
        async with sessions() as s:
            final = await repo.get_staged(s, row.id)
        return len(winners), final.status == {"approve": "approved", "reject": "rejected"}[winners[0]], \
            await count(sessions, "products") == (1 if winners[0] == "approve" else 0)

    assert run_repo(pg_engine_factory, scenario) == (1, True, True)


# ---- approve: draft product + variants + link + audit, in one transaction ----------------------
def test_approve_creates_a_draft_product_links_it_and_records_audit(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            approved = await repo.approve(s, row.id, price=4500, stock=3, actor="reviewer-1")
        async with sessions() as s:
            product = await catalogue.get_product(s, approved.product_id)
            return (approved.status, approved.stock_known, approved.approved_price, approved.approved_stock,
                    approved.missing_fields, product.status, product.is_active, product.slug, product.price, product.currency,
                    [(v.name, v.price, v.stock, v.position) for v in product.variants],
                    [(a.action, a.from_status, a.to_status, a.actor) for a in approved.audit][-1],
                    await count(sessions, "products", "is_active"))

    assert run_repo(pg_engine_factory, scenario) == (
        "approved", True, 4500, 3, [], "draft", False, "staged-1", 4500, "PKR",
        [("Burgundy", 4500, 3, 0), ("Black", 4500, 3, 1)], ("approve", "pending_review", "approved", "reviewer-1"), 0)


def test_approving_never_publishes(pg_engine_factory):
    async def scenario(sessions):
        for n in range(3):
            row, _ = await stage(sessions, n)
            async with tx(sessions) as s:
                await repo.approve(s, row.id, price=100)
        return await count(sessions, "products"), await count(sessions, "products", "status = 'active'")

    assert run_repo(pg_engine_factory, scenario) == (3, 0)


def test_approve_with_a_taken_slug_rolls_everything_back(pg_engine_factory):
    async def scenario(sessions):
        async with tx(sessions) as s:
            await catalogue.create_product(s, product_input("staged-1"))      # the draft's slug is already in the catalogue
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            with pytest.raises(Conflict):
                await repo.approve(s, row.id, price=4500, stock=1)
            still = await repo.get_staged(s, row.id)                           # same transaction: untouched
            assert (still.status, still.product_id) == ("pending_review", None)
            await repo.reject(s, row.id, "Duplicate of an existing product")   # and it is still actionable
        async with sessions() as s:
            final = await repo.get_staged(s, row.id)
        return final.status, await count(sessions, "products"), await count(sessions, "variants"), \
            [a.action for a in final.audit]

    assert run_repo(pg_engine_factory, scenario) == ("rejected", 1, 1, ["staged", "reject"])


def test_a_failed_approve_that_is_not_caught_still_leaves_nothing_behind(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1, product=draft("staged-1", name="n" * 200))     # name > 160 chars violates the catalogue CHECK
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.approve(s, row.id, price=100)
        async with sessions() as s:
            final = await repo.get_staged(s, row.id)
        return final.status, final.product_id, await count(sessions, "products"), await count(sessions, "variants")

    assert run_repo(pg_engine_factory, scenario) == ("pending_review", None, 0, 0)


@pytest.mark.parametrize("bad", [{"variants": []}, {"name": None}])
def test_approve_rejects_incomplete_drafts(pg_engine_factory, bad):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1, product=draft("staged-1", **bad))
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.approve(s, row.id, price=100)
        return await count(sessions, "products")

    assert run_repo(pg_engine_factory, scenario) == 0


@pytest.mark.parametrize("price,stock", [(-1, 0), (10, -1)])
def test_approve_rejects_negative_price_or_stock(pg_engine_factory, price, stock):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.approve(s, row.id, price=price, stock=stock)
        return await count(sessions, "products")

    assert run_repo(pg_engine_factory, scenario) == 0


def test_an_exception_after_approve_in_the_same_transaction_undoes_the_approval(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        with pytest.raises(RuntimeError):
            async with tx(sessions) as s:
                await repo.approve(s, row.id, price=100)
                raise RuntimeError("the caller's later step failed")
        async with sessions() as s:
            return (await repo.get_staged(s, row.id)).status, await count(sessions, "products")

    assert run_repo(pg_engine_factory, scenario) == ("pending_review", 0)


# ---- reject ------------------------------------------------------------------------------------
def test_reject_records_the_reason_and_audit(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            rejected = await repo.reject(s, row.id, "  Not in our range  ", actor="reviewer-2")
        return rejected.status, rejected.rejection_reason, [(a.action, a.note, a.actor) for a in rejected.audit][-1]

    assert run_repo(pg_engine_factory, scenario) == ("rejected", "Not in our range", ("reject", "Not in our range", "reviewer-2"))


def test_reject_needs_a_real_reason_and_a_pending_item(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            with pytest.raises(InvalidDraft):
                await repo.reject(s, row.id, " no ")
            await repo.reject(s, row.id, "Wrong colour palette")
        async with tx(sessions) as s:
            with pytest.raises(InvalidTransition):
                await repo.reject(s, row.id, "Rejecting twice")

    run_repo(pg_engine_factory, scenario)


# ---- publish: explicit, human, and only after approval --------------------------------------
def test_publish_activates_the_approved_draft_and_nothing_else(pg_engine_factory):
    async def scenario(sessions):
        first, _ = await stage(sessions, 1)
        other, _ = await stage(sessions, 2)
        async with tx(sessions) as s:
            approved = await repo.approve(s, first.id, price=4500, stock=2)
            await repo.approve(s, other.id, price=100)
        public_before = await count(sessions, "products", "status = 'active'")
        async with tx(sessions) as s:
            published = await repo.publish(s, first.id, actor="reviewer-1")
        async with sessions() as s:
            product = await catalogue.get_product(s, published.product_id)
            return (public_before, published.status, product.status, product.is_active, product.revision,
                    await count(sessions, "products", "status = 'active'"),
                    [(a.action, a.actor) for a in published.audit][-2:])

    assert run_repo(pg_engine_factory, scenario) == (0, "published", "active", True, 2, 1,
                                                    [("approve", "admin"), ("publish", "reviewer-1")])


def test_publish_requires_an_identified_actor_and_prior_approval(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            with pytest.raises(Conflict):
                await repo.publish(s, row.id, actor="")
            with pytest.raises(InvalidTransition):            # still pending_review: cannot jump to published
                await repo.publish(s, row.id, actor="reviewer-1")
        return await count(sessions, "products")

    assert run_repo(pg_engine_factory, scenario) == 0


def test_publish_is_not_repeatable_and_not_possible_after_rejection(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        gone, _ = await stage(sessions, 2)
        async with tx(sessions) as s:
            await repo.approve(s, row.id, price=1)
            await repo.publish(s, row.id, actor="a")
            await repo.reject(s, gone.id, "Not suitable")
        async with tx(sessions) as s:
            with pytest.raises(InvalidTransition):
                await repo.publish(s, row.id, actor="a")
            with pytest.raises(InvalidTransition):
                await repo.publish(s, gone.id, actor="a")

    run_repo(pg_engine_factory, scenario)


def test_publish_with_an_archived_product_is_refused_and_leaves_the_status_alone(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            approved = await repo.approve(s, row.id, price=1)
            await catalogue.archive_product(s, approved.product_id)
        async with tx(sessions) as s:
            with pytest.raises(ProductUnavailable):
                await repo.publish(s, row.id, actor="a")
            assert (await repo.get_staged(s, row.id)).status == "approved"        # the savepoint undid the transition
        async with sessions() as s:
            return (await repo.get_staged(s, row.id)).status, [a.action for a in (await repo.get_staged(s, row.id)).audit]

    assert run_repo(pg_engine_factory, scenario) == ("approved", ["staged", "approve"])


def test_an_ingested_product_cannot_be_activated_around_the_review(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            approved = await repo.approve(s, row.id, price=1)
        async with tx(sessions) as s:
            with pytest.raises(Conflict):
                await catalogue.publish_product(s, approved.product_id)          # the catalogue API cannot bypass review
        async with tx(sessions) as s:
            await repo.publish(s, row.id, actor="a")
            await catalogue.unpublish_product(s, approved.product_id)             # once reviewed and published, normal admin edits work
            reactivated = await catalogue.publish_product(s, approved.product_id)
        return reactivated.status

    assert run_repo(pg_engine_factory, scenario) == "active"


def test_unpublish_republish_and_archive_follow_the_state_machine(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:
            approved = await repo.approve(s, row.id, price=1)
            await repo.publish(s, row.id, actor="a")
        states = []
        for fn, kwargs in ((repo.unpublish, {}), (repo.publish, {"actor": "a"}), (repo.archive, {})):
            async with tx(sessions) as s:
                staged_row = await fn(s, row.id, **kwargs)
            async with sessions() as s:
                product = await catalogue.get_product(s, approved.product_id)
            states.append((staged_row.status, product.status))
        async with tx(sessions) as s:
            with pytest.raises(InvalidTransition):                               # archived is terminal
                await repo.publish(s, row.id, actor="a")
        return states, [a.action for a in staged_row.audit]

    assert run_repo(pg_engine_factory, scenario) == (
        [("unpublished", "draft"), ("published", "active"), ("archived", "archived")],
        ["staged", "approve", "publish", "unpublish", "publish", "archive"])


# ---- audit trail ------------------------------------------------------------------------------
def test_full_flow_audit_trail_is_strictly_ordered_and_append_only(pg_engine_factory):
    async def scenario(sessions):
        row, _ = await stage(sessions, 1)
        async with tx(sessions) as s:                                              # one transaction: timestamps tie
            await repo.approve(s, row.id, price=1)
            await repo.publish(s, row.id, actor="a")
            await repo.unpublish(s, row.id)
        async with sessions() as s:
            actions = [a.action for a in (await repo.get_staged(s, row.id)).audit]
        with pytest.raises(IntegrityError, match="append-only"):
            async with tx(sessions) as s:
                await s.execute(text("update staged_product_audit set note='x'"))
        return actions

    assert run_repo(pg_engine_factory, scenario) == ["staged", "approve", "publish", "unpublish"]
