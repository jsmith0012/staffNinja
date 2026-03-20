# Unit test for staff status service
# TODO: Add more tests after implementing logic

import pytest
from services.staff_status_service import StaffStatusService

@pytest.mark.asyncio
async def test_get_status_returns_none():
    service = StaffStatusService()
    result = await service.get_status(user_id=123)
    assert result is None
