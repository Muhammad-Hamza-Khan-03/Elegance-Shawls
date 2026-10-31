"""Admin-only sample endpoints for the Redis/arq worker foundation (new AI workloads only)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from security.admin_auth import PLATFORM_OPERATE, require_permission
from workers.queues import QueueUnavailable, enqueue, job_state

router = APIRouter(
    prefix="/v1/admin/jobs",
    tags=["AI jobs"],
    dependencies=[Depends(require_permission(PLATFORM_OPERATE))],
)


class SampleJobRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    fail_times: int = Field(default=0, ge=0, le=5)


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Job queue is unavailable")


@router.post("/sample", status_code=202)
async def enqueue_sample_job(payload: SampleJobRequest):
    try:
        job_id = await enqueue("sample_job", payload.value, payload.fail_times)
    except QueueUnavailable as exc:
        raise _unavailable() from exc
    return {"job_id": job_id}


@router.get("/{job_id}")
async def get_job(job_id: str):
    try:
        return await job_state(job_id)
    except QueueUnavailable as exc:
        raise _unavailable() from exc
