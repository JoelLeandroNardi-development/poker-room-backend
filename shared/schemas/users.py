from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CreateUser(BaseModel):
    email: str
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UpdateUser(BaseModel):
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserResponse(BaseModel):
    email: str
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: datetime

class DeleteUserResponse(BaseModel):
    message: str
    email: str
