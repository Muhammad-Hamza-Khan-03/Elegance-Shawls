"""M4-S4: server-principal-scoped, read-only deterministic suggestions."""
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from memory.principal import CustomerPrincipal, current_principal
from models.relational_model import MemoryConsent, MemoryItem, Product
from schemas.suggestion_schema import SuggestionImpressionIn, SuggestionList, SuggestionOut
from suggestions.engine import MemoryFact, ProductFact, VariantFact, build_suggestions
from suggestions.experiment import assign_arm
from repositories.memory import record_recommendation_impression

router = APIRouter(prefix="/v1/me/suggestions", tags=["Suggestions"])
FEATURE_FLAG = "m4b_explainable_recommendations"


def _models() -> tuple[str, ...]:
    return tuple(item.strip() for item in settings.llm_production_chain.split(",") if item.strip())


def _memory(row) -> MemoryFact:
    return MemoryFact(row.id, row.customer_id, row.category, row.key or "", row.value or "", row.source,
                      row.source_ref, row.version, row.status, row.expires_at, row.updated_at)


def _product(row) -> ProductFact:
    return ProductFact(
        row.id, row.slug, row.name, row.category, row.status, row.is_active, row.revision,
        row.updated_at,
        tuple(VariantFact(v.id, v.name, v.color, v.size, v.stock, v.is_active) for v in row.variants),
    )


async def _current_memory_and_products(session: AsyncSession, customer_id):
    consent = (await session.execute(select(MemoryConsent).where(MemoryConsent.customer_id == customer_id))).scalar_one_or_none()
    memories = list((await session.execute(select(MemoryItem).where(MemoryItem.customer_id == customer_id))).scalars())
    products = list((await session.execute(select(Product).where(Product.status == "active").order_by(Product.id))).scalars())
    return consent, memories, products


@router.get("", response_model=SuggestionList)
async def list_suggestions(
    request: Request,
    principal: CustomerPrincipal = Depends(current_principal),
    session: AsyncSession = Depends(get_pg_session),
):
    if (not settings.recommendations_enabled or not settings.recommendations_synthetic_only
            or settings.environment != "staging"):
        return SuggestionList(items=[], generated_at=datetime.now(timezone.utc), engine_version="m4-s4.1",
                              experiment_arm="control")
    synthetic_subject = request.headers.get("X-Synthetic-Subject", "")
    if settings.recommendations_experiment_enabled and synthetic_subject != f"synthetic:{principal.customer_id}":
        return SuggestionList(items=[], generated_at=datetime.now(timezone.utc), engine_version="m4-s4.1",
                              experiment_arm="control")
    experiment_arm = assign_arm(synthetic_subject, settings.recommendations_experiment_enabled)
    generated_at = datetime.now(timezone.utc)
    consent, memory_rows, product_rows = await _current_memory_and_products(session, principal.customer_id)
    items = build_suggestions(
        principal_customer_id=principal.customer_id,
        consented=bool(consent and consent.granted),
        memories=tuple(_memory(row) for row in memory_rows),
        products=tuple(_product(row) for row in product_rows),
        generated_at=generated_at,
        provider_models=_models(),
        declared_provider_policies=settings.llm_provider_training_policies,
        free_tier_providers=settings.llm_free_tier_providers,
    )
    return SuggestionList(items=[SuggestionOut.model_validate(asdict(item)) for item in items], generated_at=generated_at,
                          engine_version="m4-s4.1", experiment_arm=experiment_arm)


@router.post("/impressions", status_code=204)
async def record_suggestion_impression(
    body: SuggestionImpressionIn,
    request: Request,
    response: Response,
    principal: CustomerPrincipal = Depends(current_principal),
    session: AsyncSession = Depends(get_pg_session),
):
    if (not settings.recommendations_enabled or not settings.recommendations_synthetic_only
            or settings.environment != "staging"):
        return None
    synthetic_subject = request.headers.get("X-Synthetic-Subject", "")
    if synthetic_subject != f"synthetic:{principal.customer_id}":
        raise HTTPException(422, "synthetic subject required")
    if body.position < 0 or not 16 <= len(body.request_id) <= 128:
        raise HTTPException(422, "invalid impression")
    if body.context not in {"recommendation_strip", "recommendation_grid", "assistant"}:
        raise HTTPException(422, "invalid impression")
    if body.experiment_arm not in {"control", "treatment"}:
        raise HTTPException(422, "invalid impression")
    if body.experiment_arm != assign_arm(synthetic_subject, settings.recommendations_experiment_enabled):
        raise HTTPException(422, "invalid impression")
    generated_at = datetime.now(timezone.utc)
    consent, memory_rows, product_rows = await _current_memory_and_products(session, principal.customer_id)
    candidates = build_suggestions(
        principal_customer_id=principal.customer_id,
        consented=bool(consent and consent.granted),
        memories=tuple(_memory(row) for row in memory_rows),
        products=tuple(_product(row) for row in product_rows),
        generated_at=generated_at,
        provider_models=_models(),
        declared_provider_policies=settings.llm_provider_training_policies,
        free_tier_providers=settings.llm_free_tier_providers,
    )
    matched = next((candidate for candidate in candidates if candidate.id == body.recommendation_id), None)
    if matched is None or matched.product_id != body.product_id:
        raise HTTPException(422, "recommendation is not server-issued")
    evidence = matched.reason.product_evidence
    if evidence.variant_id != body.variant_id or evidence.product_revision != body.catalogue_revision:
        raise HTTPException(422, "recommendation evidence mismatch")
    if tuple(body.source_memory_ids) != matched.reason.source_memory_ids:
        raise HTTPException(422, "recommendation provenance mismatch")
    memory_versions = {row.id: row.version for row in memory_rows}
    if body.preference_version != memory_versions.get(matched.reason.source_memory_ids[0], -1):
        raise HTTPException(422, "recommendation preference mismatch")
    await record_recommendation_impression(
        session, customer_id=principal.customer_id, recommendation_id=body.recommendation_id,
        product_id=body.product_id, variant_id=body.variant_id, request_id=body.request_id,
        position=body.position, context=body.context, feature_flag=FEATURE_FLAG,
        experiment_arm=body.experiment_arm, preference_version=body.preference_version,
        catalogue_revision=body.catalogue_revision, source_memory_ids=body.source_memory_ids,
        created_at=datetime.now(timezone.utc),
    )
    await session.commit()
    response.status_code = 204
    return None
