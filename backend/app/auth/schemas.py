from pydantic import BaseModel, field_validator
from typing import Optional
import re


class UserCreate(BaseModel):
    email: str
    password: str

    @field_validator('email')
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()

    @field_validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class AdminUserCreate(BaseModel):
    """Schema for admin-created users."""
    email: str
    password: str
    role: str = "user"

    @field_validator('email')
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()

    @field_validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    @field_validator('role')
    def validate_role(cls, v):
        if v not in ('admin', 'user'):
            raise ValueError('Role must be "admin" or "user"')
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    sub: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: str


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator('role')
    def validate_role(cls, v):
        if v is not None and v not in ('admin', 'user'):
            raise ValueError('Role must be "admin" or "user"')
        return v
