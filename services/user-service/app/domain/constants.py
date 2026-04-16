from __future__ import annotations

from enum import StrEnum

class TableName(StrEnum):
    USERS = "users"

class UserEventType(StrEnum):
    CREATED = "user.created"
    UPDATED = "user.updated"
    DELETED = "user.deleted"

class DataKey(StrEnum):
    EMAIL = "email"
    DISPLAY_NAME = "display_name"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"

class ErrorMessage(StrEnum):
    USER_ALREADY_EXISTS = "User already exists"
    USER_NOT_FOUND = "User not found"

class ResponseMessage(StrEnum):
    DELETED = "deleted"
