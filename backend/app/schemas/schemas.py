from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime

# --- Auth ---
class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long and not only whitespace")
        if not any(char.isalpha() for char in v) or not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one letter and one number")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

# --- Projects & Environments ---
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class EnvironmentOut(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True

class MemberOut(BaseModel):
    id: str
    user_id: str
    role: str
    name: str
    email: str

class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime
    role: Optional[str] = None
    environments: List[EnvironmentOut] = []

    class Config:
        from_attributes = True

class AddMemberRequest(BaseModel):
    email: EmailStr

# --- Variables ---
class VariableCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str
    is_sensitive: bool = False

class VariableUpdate(BaseModel):
    value: Optional[str] = None
    is_sensitive: Optional[bool] = None

class VariableOut(BaseModel):
    id: str
    key: str
    value: str
    is_sensitive: bool
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Smart Bulk Import ---
class ImportParseRequest(BaseModel):
    raw_env: str

class DiffItem(BaseModel):
    key: str
    old_value: Optional[str] = None
    new_value: str
    status: str
    is_sensitive: bool = False
    is_existing_sensitive: bool = False

class BulkImportCommitRequest(BaseModel):
    raw_env: Optional[str] = None
    items: Optional[List[DiffItem]] = None
    sensitive_keys: List[str] = Field(default_factory=list)

# --- History ---
class HistoryLogOut(BaseModel):
    id: str
    action: str
    key: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    user_name: str
    created_at: datetime

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("New password must be at least 8 characters long and not only whitespace")
        if not any(char.isalpha() for char in v) or not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one letter and one number")
        return v
