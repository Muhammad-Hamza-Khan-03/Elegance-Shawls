"""M4-S4 deterministic, reasoned suggestions.

This module is deliberately pure: it receives server-selected records and returns typed
candidates. It performs no inference, model/provider call, network access, persistence,
or mutation. Matching is exact and allow-listed; unknown facts fail closed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Literal, Sequence

from memory import policy

ENGINE_VERSION = "m4-s4.1"
# Catalogue data is eligible for suggestions for at most one day from the server-observed
# freshness timestamp. Missing, future, or older timestamps fail closed.
CATALOGUE_FRESHNESS_MAX_AGE = timedelta(hours=24)
_CANDIDATE_NAMESPACE = uuid.UUID("5c1ab2b3-bd04-4c35-8ba6-42d0b3d7ee40")

ReasonCode = Literal["explicit_colour_match", "explicit_size_match", "explicit_category_match", "explicit_style_match"]
DecisionCode = Literal["allowed", "needs_review"]


@dataclass(frozen=True)
class SuggestionPolicyDecision:
    consented: bool
    provider_allowed: bool
    provider_reason: str
    decision: DecisionCode
    version: str = ENGINE_VERSION


@dataclass(frozen=True)
class MemoryFact:
    id: uuid.UUID
    customer_id: uuid.UUID
    category: str
    key: str
    value: str
    source: str
    source_ref: str | None
    version: int
    status: str
    expires_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProductFact:
    id: uuid.UUID
    slug: str
    name: str
    category: str
    status: str
    is_active: bool
    revision: int
    catalogue_fresh_at: datetime | None
    variants: tuple["VariantFact", ...] = ()


@dataclass(frozen=True)
class VariantFact:
    id: uuid.UUID
    name: str
    colour: str | None
    size: str
    stock: int
    is_active: bool


@dataclass(frozen=True)
class ProductEvidence:
    product_id: uuid.UUID
    product_slug: str
    product_name: str
    product_revision: int
    variant_id: uuid.UUID | None
    matched_field: str
    matched_value: str


@dataclass(frozen=True)
class SuggestionReason:
    code: ReasonCode
    text: str
    source_memory_ids: tuple[uuid.UUID, ...]
    source_provenance: tuple[str, ...]
    product_evidence: ProductEvidence
    policy: SuggestionPolicyDecision
    generated_at: datetime
    engine_version: str = ENGINE_VERSION


@dataclass(frozen=True)
class SuggestionCandidate:
    id: uuid.UUID
    customer_id: uuid.UUID
    product_id: uuid.UUID
    reason: SuggestionReason
    generated_at: datetime
    engine_version: str = ENGINE_VERSION


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _policy(consented: bool, models: Iterable[object], declared: str | None, free_tier: str | None) -> SuggestionPolicyDecision:
    gate = policy.provider_gate(tuple(models), declared, free_tier)
    allowed = consented is True and gate.allowed
    return SuggestionPolicyDecision(
        consented=consented is True,
        provider_allowed=gate.allowed,
        provider_reason="cleared" if gate.allowed else gate.reason,
        decision="allowed" if allowed else "needs_review",
    )


def _matching_facts(memory: MemoryFact, product: ProductFact) -> tuple[ReasonCode, str, ProductEvidence] | None:
    """Match only explicit, non-sensitive allow-listed facts; never inspect free text semantically."""
    if memory.category != "preference" or memory.source not in {"user_explicit", "memory_page"}:
        return None
    value = _normalise(memory.value)
    key = memory.key.casefold()
    variants = tuple(v for v in product.variants if v.is_active and v.stock > 0)
    if key in {"colour", "color"}:
        for variant in variants:
            if variant.colour and _normalise(variant.colour) == value:
                return "explicit_colour_match", "Matches your explicit colour preference.", ProductEvidence(
                    product.id, product.slug, product.name, product.revision, variant.id, "variant.colour", variant.colour)
    elif key == "size":
        for variant in variants:
            if _normalise(variant.size) == value:
                return "explicit_size_match", "Matches your explicit size preference.", ProductEvidence(
                    product.id, product.slug, product.name, product.revision, variant.id, "variant.size", variant.size)
    elif key == "category" and _normalise(product.category) == value:
        return "explicit_category_match", "Matches the category you explicitly selected.", ProductEvidence(
            product.id, product.slug, product.name, product.revision, None, "product.category", product.category)
    elif key == "style" and (_normalise(product.slug) == value or _normalise(product.name) == value):
        return "explicit_style_match", "Matches the style you explicitly selected.", ProductEvidence(
            product.id, product.slug, product.name, product.revision, None, "product.name", product.name)
    return None


def _memory_key(memory: MemoryFact) -> str:
    """Canonicalize only the allow-listed key aliases for ambiguity detection."""
    key = memory.key.casefold()
    return "colour" if key == "color" else key


def build_suggestions(
    *,
    principal_customer_id: uuid.UUID,
    consented: bool,
    memories: Sequence[MemoryFact],
    products: Sequence[ProductFact],
    generated_at: datetime,
    provider_models: Iterable[object],
    declared_provider_policies: str | None = None,
    free_tier_providers: str | None = None,
) -> tuple[SuggestionCandidate, ...]:
    """Return deterministic candidates, or an empty tuple on any policy/ownership failure.

    The caller must supply rows selected for the server principal. We still re-check ownership,
    lifecycle and freshness here so a stale/deleted/cross-user row cannot become a suggestion.
    """
    decision = _policy(consented, provider_models, declared_provider_policies, free_tier_providers)
    if decision.decision != "allowed":
        return ()
    usable = tuple(sorted(
        (m for m in memories
         if m.customer_id == principal_customer_id and m.status == "active" and m.source in {"user_explicit", "memory_page"}
         and m.category == "preference" and m.version >= 1 and m.expires_at > generated_at
         and m.key and m.value),
        key=lambda m: str(m.id),
    ))
    current_products = tuple(sorted(
        (p for p in products
         if p.status == "active" and p.is_active and p.revision >= 1
         and p.catalogue_fresh_at is not None
         and p.catalogue_fresh_at <= generated_at
         and generated_at - p.catalogue_fresh_at <= CATALOGUE_FRESHNESS_MAX_AGE),
        key=lambda p: str(p.id),
    ))
    # Multiple active rows for one customer/key are ambiguous even when their values happen
    # to agree. Do not deduplicate them or let the product-level `seen` guard choose a winner.
    key_counts: dict[str, int] = {}
    for memory in usable:
        key = _memory_key(memory)
        key_counts[key] = key_counts.get(key, 0) + 1
    ambiguous_keys = {key for key, count in key_counts.items() if count > 1}
    usable = tuple(memory for memory in usable if _memory_key(memory) not in ambiguous_keys)
    result: list[SuggestionCandidate] = []
    seen: set[tuple[uuid.UUID, ReasonCode]] = set()
    for memory in usable:
        for product in current_products:
            match = _matching_facts(memory, product)
            if match is None:
                continue
            code, text, evidence = match
            if (product.id, code) in seen:
                continue
            seen.add((product.id, code))
            reason = SuggestionReason(
                code=code,
                text=text,
                source_memory_ids=(memory.id,),
                source_provenance=(memory.source_ref or memory.source,),
                product_evidence=evidence,
                policy=decision,
                generated_at=generated_at,
            )
            candidate_id = uuid.uuid5(_CANDIDATE_NAMESPACE, f"{principal_customer_id}:{product.id}:{code}:{memory.id}")
            result.append(SuggestionCandidate(candidate_id, principal_customer_id, product.id, reason, generated_at))
    return tuple(sorted(result, key=lambda candidate: str(candidate.id)))
