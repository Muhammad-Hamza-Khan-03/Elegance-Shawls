"""Fail-closed guard for queued memory extraction (M4-C readiness only).

This module has no provider or queue side effects. A future worker must call
``accept_result`` immediately before any PostgreSQL memory write and discard the
result when it returns false. The captured privacy epoch makes retries and
worker restarts safe after deletion, correction, or consent disablement.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExtractionJob:
    customer_id: str
    memory_version: int
    source_at: datetime
    key: str


def accept_result(job: ExtractionJob, *, current_memory_version: int, memory_enabled: bool,
                  tombstone_at: datetime | None, now: datetime) -> bool:
    """Return true only when queued work is still authorized and not superseded."""
    if not memory_enabled:
        return False
    if current_memory_version != job.memory_version:
        return False
    if tombstone_at is not None and job.source_at <= tombstone_at:
        return False
    if now < job.source_at:
        return False
    return True
