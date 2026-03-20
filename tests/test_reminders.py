# Unit test for reminder service
# TODO: Add more tests after implementing logic

import pytest
from services.reminder_service import ReminderService

@pytest.mark.asyncio
async def test_schedule_reminder_noop():
    service = ReminderService()
    result = await service.schedule_reminder(user_id=123, message="Test", when="tomorrow")
    assert result is None
