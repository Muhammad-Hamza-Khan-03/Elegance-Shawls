"""M4-S4: server-principal-scoped, read-only deterministic suggestions."""
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from configuration.config import settings
from database.pg import get_pg_session
from memory.principal import CustomerPrincipal, current_principal
from models.relational_model import MemoryConsent, MemoryItem, Product
from schemas.suggestion_schema import SuggestionList, SuggestionOut
from suggestions.engine import MemoryFact, ProductFact, VariantFact, build_suggestions

router = APIRouter(prefix="/v1/me/suggestions", tags=["Suggestions"])


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
    principal: CustomerPrincipal = Depends(current_principal),
    session: AsyncSession = Depends(get_pg_session),
):
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
                          engine_version="m4-s4.1")
