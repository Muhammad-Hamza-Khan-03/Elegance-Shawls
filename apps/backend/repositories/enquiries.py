"""Enquiry references: validate a cart against the live catalogue and persist a minimal snapshot. Callers own the transaction."""
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.relational_model import Enquiry, Product, Variant
from repositories import RepositoryError

# No 0/O/1/I: a reference is read aloud and retyped on WhatsApp. 31^6 is ~887M values.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERENCE_LENGTH = 6
_ATTEMPTS = 5


@dataclass(frozen=True)
class Line:
    product_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int
    unit_price: int
    currency: str


class StaleCart(RepositoryError):
    """The cart no longer matches the catalogue. `issues` say, per variant, what changed."""

    def __init__(self, issues: list[dict]):
        super().__init__("Cart no longer matches the catalogue")
        self.issues = issues


def new_reference() -> str:
    return "ES-" + "".join(secrets.choice(ALPHABET) for _ in range(REFERENCE_LENGTH))


def _issue(line: Line, reason: str, **extra) -> dict:
    return {"product_id": str(line.product_id), "variant_id": str(line.variant_id), "reason": reason, **extra}


async def create_enquiry(session: AsyncSession, lines: list[Line]) -> Enquiry:
    rows = (await session.execute(
        select(Variant, Product).join(Product, Product.id == Variant.product_id)
        .where(Variant.id.in_([line.variant_id for line in lines]))
    )).all()
    live = {variant.id: (variant, product) for variant, product in rows}

    issues, snapshot = [], []
    for line in lines:
        found = live.get(line.variant_id)
        if not found or found[1].id != line.product_id or found[1].status != "active" or not found[0].is_active:
            issues.append(_issue(line, "unavailable"))
            continue
        variant, product = found
        if variant.stock < 1:
            issues.append(_issue(line, "out_of_stock"))
        elif line.quantity > variant.stock:
            issues.append(_issue(line, "insufficient_stock", available=variant.stock))
        elif line.unit_price != variant.price or line.currency != variant.currency:
            issues.append(_issue(line, "price_changed", current_price=variant.price, current_currency=variant.currency))
        else:
            snapshot.append({
                "product_id": str(product.id), "variant_id": str(variant.id), "product": product.name,
                "color": variant.color, "size": variant.size, "quantity": line.quantity, "unit_price": variant.price,
            })
    if issues:
        raise StaleCart(issues)

    currency = lines[0].currency
    total = sum(item["unit_price"] * item["quantity"] for item in snapshot)
    for _ in range(_ATTEMPTS):
        enquiry = Enquiry(reference=new_reference(), items=snapshot, currency=currency, total=total)
        try:
            async with session.begin_nested():     # a reference collision undoes only this insert
                session.add(enquiry)
                await session.flush()
            return enquiry
        except IntegrityError:
            continue
    raise RepositoryError("Could not allocate a unique enquiry reference")


async def get_by_reference(session: AsyncSession, reference: str) -> Enquiry | None:
    return (await session.execute(select(Enquiry).where(Enquiry.reference == reference.strip().upper()))).scalar_one_or_none()


async def list_enquiries(session: AsyncSession, limit: int) -> list[Enquiry]:
    return list((await session.execute(select(Enquiry).order_by(Enquiry.created_at.desc(), Enquiry.id.desc()).limit(limit))).scalars())


async def catalogue_snapshot(session: AsyncSession, product_ids: list[uuid.UUID]) -> dict:
    """Current state of the given products in the action kernel's shape (read-only; includes slug for the cart handoff)."""
    rows = (await session.execute(
        select(Product, Variant).join(Variant, Variant.product_id == Product.id, isouter=True).where(Product.id.in_(product_ids))
    )).all()
    out: dict = {}
    for product, variant in rows:
        entry = out.setdefault(str(product.id), {"id": str(product.id), "slug": product.slug, "status": product.status,
                                                 "is_active": product.is_active, "revision": product.revision, "variants": []})
        if variant is not None:
            entry["variants"].append({"id": str(variant.id), "is_active": variant.is_active, "price": variant.price,
                                      "currency": variant.currency, "stock": variant.stock})
    return out
