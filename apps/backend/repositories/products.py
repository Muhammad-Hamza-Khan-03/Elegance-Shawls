"""Catalogue repository: products and their variants. Callers own the transaction (no commits here)."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.query import ParsedQuery
from catalog.search import CURRENCY
from models.relational_model import Product, StagedProduct, Variant
from repositories import Conflict, InvalidDraft, NotFound
from utils.colour_vocabulary import spellings

Key = tuple[datetime, uuid.UUID]  # (created_at, id): the cursor position of a product


@dataclass
class VariantInput:
    name: str
    image_url: str
    price: int
    stock: int = 0
    color: str | None = None
    size: str = "Free Size"
    currency: str = "PKR"
    description: str | None = None
    id: uuid.UUID | None = None  # an existing variant to keep when replacing a product


@dataclass
class ProductInput:
    slug: str
    name: str
    cover_image_url: str
    variants: list[VariantInput]
    price: int | None = None
    category: str = "shawls"
    status: str = "draft"  # callers must ask for anything else; "active" is a deliberate publish
    images: list[str] = field(default_factory=list)
    main_description: str | None = None
    currency: str = "PKR"
    material: str | None = None
    sizing: str | None = None
    weight: str | None = None
    item_number: str | None = None


@dataclass
class Page:
    items: list[Product]
    next_after: Key | None  # pass back as `after` for the next page


def _columns(data: ProductInput) -> dict:
    """Product columns, normalised like the public schema: cover image listed first, price defaults to the cheapest variant."""
    if not data.variants:
        raise InvalidDraft("A product needs at least one variant")
    images = list(data.images) or [data.cover_image_url]
    if data.cover_image_url not in images:
        images.insert(0, data.cover_image_url)
    price = data.price if data.price is not None else min(v.price for v in data.variants)
    return {
        "slug": data.slug, "name": data.name, "category": data.category, "status": data.status,
        "cover_image_url": data.cover_image_url, "images": images, "main_description": data.main_description,
        "price": price, "currency": data.currency.upper(), "material": data.material, "sizing": data.sizing,
        "weight": data.weight, "item_number": data.item_number,
    }


def _variant(position: int, data: VariantInput) -> Variant:
    return Variant(
        position=position, name=data.name, color=data.color, size=data.size, image_url=data.image_url,
        price=data.price, currency=data.currency.upper(), stock=data.stock, description=data.description,
    )


def _is_slug_conflict(exc: IntegrityError) -> bool:
    return "uq_products_slug" in str(exc.orig)


async def reload(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    """Fresh read with variants (also picks up generated columns after a write)."""
    return await session.get(Product, product_id, populate_existing=True)


async def create_product(session: AsyncSession, data: ProductInput) -> Product:
    """Insert a product with its variants (positions follow the submitted order)."""
    product = Product(**_columns(data), variants=[_variant(i, v) for i, v in enumerate(data.variants)])
    try:
        async with session.begin_nested():  # a duplicate slug undoes only this insert
            session.add(product)
            await session.flush()
    except IntegrityError as exc:
        if _is_slug_conflict(exc):
            raise Conflict("Product slug already exists", Conflict.SLUG_EXISTS) from exc
        raise InvalidDraft(str(exc.orig)) from exc
    return await reload(session, product.id)


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    """Any lifecycle state (admin)."""
    return await session.get(Product, product_id)


async def get_public_product_by_slug(session: AsyncSession, slug: str) -> Product | None:
    stmt = select(Product).where(Product.slug == slug.lower(), Product.status == "active")
    return (await session.execute(stmt)).scalar_one_or_none()


def _term_match(term: str):
    """One search term must appear (case-insensitive substring) in a product field or in one of its variants."""
    like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    fields = (Product.name, Product.slug, Product.material, Product.item_number, Product.main_description)
    in_variant = exists().where(Variant.product_id == Product.id,
                                or_(Variant.name.ilike(like, escape="\\"), Variant.color.ilike(like, escape="\\")))
    return or_(*(f.ilike(like, escape="\\") for f in fields), in_variant)


@dataclass
class VariantFilter:
    """Constraints that one and the same purchasable variant must satisfy together."""
    colour: str | None = None  # canonical vocabulary value
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool = False


def _variant_match(f: VariantFilter):
    """EXISTS over a single variant row, so colour, price and stock can never be satisfied by different variants."""
    norm = lambda col: func.regexp_replace(func.lower(func.trim(col)), r"\s+", " ", "g")  # noqa: E731
    conds = [Variant.product_id == Product.id, Variant.is_active.is_(True)]
    if f.colour:
        raw = spellings(f.colour)
        # Same precedence as colour_vocabulary.resolve: the name only counts when colour is null/blank.
        conds.append(or_(norm(Variant.color).in_(raw),
                         and_(func.coalesce(func.trim(Variant.color), "") == "", norm(Variant.name).in_(raw))))
    if f.min_price is not None:
        conds.append(Variant.price >= f.min_price)
    if f.max_price is not None:
        conds.append(Variant.price <= f.max_price)
    if f.in_stock:
        conds.append(Variant.stock > 0)
    return exists().where(*conds)


async def list_products(session: AsyncSession, *, public: bool, limit: int, after: Key | None = None,
                        q: str | None = None, variant: VariantFilter | None = None) -> Page:
    """Newest first with keyset pagination on (created_at, id); public means active products only.
    `q` is whitespace-separated terms that must all match (shortcut: ILIKE scan, move to full-text/trigram with the M1 index)."""
    stmt = select(Product).order_by(Product.created_at.desc(), Product.id.desc()).limit(limit + 1)
    if public:
        stmt = stmt.where(Product.status == "active")
    if q:
        stmt = stmt.where(and_(*(_term_match(t) for t in q.split()[:8])))
    if variant is not None:
        stmt = stmt.where(_variant_match(variant))
    if after is not None:
        stmt = stmt.where(tuple_(Product.created_at, Product.id) < tuple_(*after))
    rows = list((await session.execute(stmt)).scalars())
    if len(rows) <= limit:
        return Page(rows, None)
    rows.pop()
    return Page(rows, (rows[-1].created_at, rows[-1].id))


async def _has_unpublished_review(session: AsyncSession, product_id: uuid.UUID) -> bool:
    status = (await session.execute(
        select(StagedProduct.status).where(StagedProduct.product_id == product_id).limit(1))).scalar_one_or_none()
    return status is not None and status != "published"


async def set_status(session: AsyncSession, product_id: uuid.UUID, status: str, *, enforce_review: bool = True) -> Product:
    """Change lifecycle state. Products that came from ingestion go public only through the staged
    publish action, so activating one directly is refused (enforce_review=False is for that action)."""
    if enforce_review and status == "active" and await _has_unpublished_review(session, product_id):
        raise Conflict("Ingested products must be published through the staged review workflow", Conflict.REVIEW_REQUIRED)
    result = await session.execute(
        update(Product).where(Product.id == product_id)
        .values(status=status, updated_at=func.now(), revision=Product.revision + 1).returning(Product.id))
    if result.scalar_one_or_none() is None:
        raise NotFound("Product not found")
    return await reload(session, product_id)


async def publish_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    return await set_status(session, product_id, "active")


async def unpublish_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    return await set_status(session, product_id, "draft")


async def archive_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    """Soft delete: products are archived, never removed."""
    return await set_status(session, product_id, "archived")


async def set_state_unless_archived(session: AsyncSession, product_id: uuid.UUID, status: str) -> bool:
    """Used by the staged-review actions: never resurrects an archived product. True when a row changed."""
    result = await session.execute(
        update(Product).where(Product.id == product_id, Product.status != "archived")
        .values(status=status, updated_at=func.now(), revision=Product.revision + 1).returning(Product.id))
    return result.scalar_one_or_none() is not None


async def set_variant_stock(session: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID, stock: int) -> Product:
    """Absolute stock set as ONE atomic statement; concurrent updates never corrupt a row and a
    negative value is refused before any SQL runs."""
    if stock < 0:
        raise InvalidDraft("Stock cannot be negative")
    result = await session.execute(
        update(Variant).where(Variant.id == variant_id, Variant.product_id == product_id)
        .values(stock=stock).returning(Variant.id))
    if result.scalar_one_or_none() is None:
        raise NotFound("Product or variant not found")
    await session.execute(
        update(Product).where(Product.id == product_id)
        .values(updated_at=func.now(), revision=Product.revision + 1))
    return await reload(session, product_id)


async def replace_product(session: AsyncSession, product_id: uuid.UUID, data: ProductInput) -> Product:
    """Full replacement (PUT): known variant ids are kept, new ones are created, omitted ones are removed."""
    product = await session.get(Product, product_id, with_for_update=True, populate_existing=True)
    if product is None:
        raise NotFound("Product not found")
    if data.status == "active" and await _has_unpublished_review(session, product_id):
        raise Conflict("Ingested products must be published through the staged review workflow", Conflict.REVIEW_REQUIRED)
    columns = _columns(data)
    existing = {v.id: v for v in product.variants}
    try:
        async with session.begin_nested():
            for name, value in columns.items():
                setattr(product, name, value)
            product.revision = Product.revision + 1
            product.updated_at = func.now()
            kept: list[Variant] = []
            for position, submitted in enumerate(data.variants):
                row = existing.pop(submitted.id, None) if submitted.id else None
                if row is None:
                    kept.append(_variant(position, submitted))
                    continue
                row.position, row.name, row.color, row.size = position, submitted.name, submitted.color, submitted.size
                row.image_url, row.price, row.currency = submitted.image_url, submitted.price, submitted.currency.upper()
                row.stock, row.description = submitted.stock, submitted.description
                kept.append(row)
            product.variants = kept
            await session.flush()
    except IntegrityError as exc:
        if _is_slug_conflict(exc):
            raise Conflict("Product slug already exists", Conflict.SLUG_EXISTS) from exc
        raise InvalidDraft(str(exc.orig)) from exc
    return await reload(session, product_id)


async def search_batch(session: AsyncSession, q: ParsedQuery, after: Key | None, n: int) -> list[Product]:
    """Read-only: the next `n` active products in catalogue order that MAY match `q`.

    The predicates only ever narrow to a superset of the true matches (category, numeric/stock bounds on
    one variant, ASCII text tokens as substrings); catalog.search.evaluate decides exactly. Same
    (created_at, id) order and keyset as list_products.
    """
    stmt = select(Product).where(Product.status == "active")
    if q.categories:
        stmt = stmt.where(Product.category.in_(q.categories))
    variant = [Variant.product_id == Product.id, Variant.is_active]
    if q.min_price is not None or q.max_price is not None:
        variant.append(Variant.currency == CURRENCY)
    if q.min_price is not None:
        variant.append(Variant.price >= q.min_price)
    if q.max_price is not None:
        variant.append(Variant.price <= q.max_price)
    if q.in_stock:
        variant.append(Variant.stock > 0)
    if len(variant) > 2:
        stmt = stmt.where(exists().where(*variant))
    for token in q.text:
        if token.isascii():  # other scripts are normalised in Python only, so they are left to evaluate()
            stmt = stmt.where(or_(
                *[c.icontains(token, autoescape=True) for c in (Product.name, Product.main_description, Product.material, Product.item_number)],
                exists().where(Variant.product_id == Product.id, Variant.name.icontains(token, autoescape=True))))
    if after is not None:
        stmt = stmt.where(tuple_(Product.created_at, Product.id) < tuple_(*after))
    stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc()).limit(n)
    return list((await session.execute(stmt)).scalars())
