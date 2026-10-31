"""Admin-only read and operator refresh routes for advisory LLM model discovery."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from llm.model_discovery import catalog, refresh_models
from security.admin_auth import PLATFORM_OPERATE, require_permission

router = APIRouter(prefix="/v1", tags=["LLM models"])
admin_router = APIRouter(prefix="/v1/admin/llm/models", tags=["LLM models"], dependencies=[Depends(require_permission(PLATFORM_OPERATE))])


class RefreshResult(BaseModel):
    providers: dict[str, str]


@router.get("/llm/models", dependencies=[Depends(require_permission(PLATFORM_OPERATE))])
async def get_llm_models():
    return await catalog()


@admin_router.post("/refresh", response_model=RefreshResult)
async def refresh_llm_models(provider: Literal["groq", "gemini"] | None = Query(default=None)):
    return {"providers": await refresh_models(provider)}
