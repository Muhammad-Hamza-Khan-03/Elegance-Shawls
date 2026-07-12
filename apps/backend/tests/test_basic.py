import pytest
import asyncio

def test_basic():
    """Basic test to ensure testing framework works"""
    assert True

def test_math_operations():
    """Test basic math operations"""
    assert 2 + 2 == 4
    assert 10 - 5 == 5

@pytest.mark.asyncio
async def test_async_basic():
    """Basic async test"""
    result = await asyncio.sleep(0.001)
    assert result is None
