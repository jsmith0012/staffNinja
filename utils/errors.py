class StaffNinjaError(Exception):
    """Base exception for staffNinja bot."""
    pass

class DatabaseError(StaffNinjaError):
    pass

class NotFoundError(StaffNinjaError):
    pass
