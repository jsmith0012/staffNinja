import pytest
import db.queries

@pytest.mark.asyncio
async def test_search_documents_stage1():
    """Verify that stage 1 document search works."""
    res = await db.queries.search_documents_stage1("refund policy", None)
    assert isinstance(res, list)

@pytest.mark.asyncio
async def test_search_documents_fallback():
    """Verify fallback document search works."""
    res = await db.queries.search_documents_fallback(["%refund%", "%policy%"], None)
    assert isinstance(res, list)
