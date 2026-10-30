"""Enquiry references for the WhatsApp handoff.

POST /v1/enquiries validates a cart at the server boundary and returns a short reference for the prefilled
WhatsApp message. It creates no order, reserves no stock and sends no message: a person still taps wa.me.
Staff look references up through the admin routes (existing admin auth).
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.pg import get_pg_session
from repositories import enquiries as repo
from repositories.enquiries import Line, StaleCart
from security.admin_auth import require_admin

router = APIRouter(prefix="/v1/enquiries", tags=["Enquiries"])
admin_router = APIRouter(prefix="/v1/admin/enquiries", tags=["Enquiries"], dependencies=[Depends(require_admin)])


class EnquiryLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=1000)
    unit_price: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class EnquiryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[EnquiryLine] = Field(min_length=1, max_length=50)


class EnquiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reference: str
    items: list[dict]
    currency: str
    total: int
    created_at: datetime


@router.post("", response_model=EnquiryResponse, status_code=201)
async def create_enquiry(payload: EnquiryRequest, session: AsyncSession = Depends(get_pg_session)):
    variant_ids = [line.variant_id for line in payload.items]
    if len(set(variant_ids)) != len(variant_ids):
        raise HTTPException(status_code=422, detail="Each product option may appear only once")
    lines = [Line(l.product_id, l.variant_id, l.quantity, l.unit_price, l.currency.upper()) for l in payload.items]
    if len({line.currency for line in lines}) > 1:
        raise HTTPException(status_code=422, detail="All items must use the same currency")
    try:
        async with session.begin():
            return await repo.create_enquiry(session, lines)
    except StaleCart as exc:
        raise HTTPException(status_code=409, detail={"code": "cart_stale", "issues": exc.issues}) from exc


@admin_router.get("", response_model=list[EnquiryResponse])
async def list_enquiries(
    reference: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_pg_session),
):
    if reference:
        found = await repo.get_by_reference(session, reference)
        return [found] if found else []
    return await repo.list_enquiries(session, limit)


@admin_router.get("/{reference}", response_model=EnquiryResponse)
async def get_enquiry(reference: str, session: AsyncSession = Depends(get_pg_session)):
    found = await repo.get_by_reference(session, reference)
    if not found:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return found
