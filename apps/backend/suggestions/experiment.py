"""Deterministic synthetic-only experiment assignment for M4 Batch B."""
from __future__ import annotations

import hashlib
from typing import Literal

ExperimentArm = Literal["control", "treatment"]


def assign_arm(subject: str, enabled: bool) -> ExperimentArm:
    """Assign a stable 50/50 arm without treating a customer identifier as client authority."""
    if not enabled:
        return "control"
    digest = hashlib.sha256(subject.encode("utf-8")).digest()
    return "treatment" if digest[0] >= 128 else "control"
