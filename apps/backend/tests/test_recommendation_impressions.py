import uuid
from datetime import datetime, timezone

import pytest

from repositories.memory import record_recommendation_impression


@pytest.mark.asyncio
async def test_impression_insert_is_append_only_and_duplicate_safe():
    class Result:
        rowcount = 1

    class Session:
        async def execute(self, statement):
            compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
            assert "ON CONFLICT" in compiled
            return Result()

    assert await record_recommendation_impression(Session(), customer_id=uuid.uuid4(), recommendation_id=uuid.uuid4(),
                                   product_id=uuid.uuid4(), variant_id=None, request_id="request-opaque-001",
                                   position=0, context="recommendation_grid", feature_flag="m4b_explainable_recommendations",
                                   experiment_arm="treatment", preference_version=1, catalogue_revision=2,
                                   source_memory_ids=(uuid.uuid4(),), created_at=datetime.now(timezone.utc))