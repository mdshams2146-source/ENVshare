from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# --- Auth ---
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

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
    name: str
    description: Optional[str] = None

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
    key: str
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
    status: str  # NEW, UPDATE, UNCHANGED
    is_sensitive: bool = False

class BulkImportCommitRequest(BaseModel):
    items: List[DiffItem]

# --- History ---
class HistoryLogOut(BaseModel):
    id: str
    action: str
    key: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    user_name: str
    created_at: datetime