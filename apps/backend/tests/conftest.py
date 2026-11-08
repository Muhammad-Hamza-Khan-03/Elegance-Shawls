import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def isolate_optional_runtime_configuration(request, monkeypatch):
    """Keep the default suite independent of a developer's local .env."""
    from configuration.config import settings
    from llm import gateway
    from security import rate_limit

    for name, value in (
        ("embedding_enabled", False),
        ("embedding_provider", ""),
        ("local_semantic_search_enabled", False),
        ("local_e5_model_path", ""),
        ("local_e5_model_revision", ""),
        ("local_gemma_model_path", ""),
        ("local_gemma_model_revision", ""),
        ("redis_url", ""),
    ):
        monkeypatch.setattr(settings, name, value)

    # Integration tests provision Redis explicitly; keep the real client path available there.
    if "tests/integration/" not in request.node.nodeid.replace("\\", "/"):
        monkeypatch.setattr(gateway, "get_redis", lambda: None)
        monkeypatch.setattr(rate_limit, "get_redis", lambda: None)
