from pydantic import BaseModel, EmailStr, UUID4
from typing import Optional
from enum import Enum

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserLoginMicrosoft(BaseModel):
    name: str
    email: EmailStr
    id: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    designation: Optional[str] = None

class UserCreateMicrosoft(BaseModel):
    name: str
    email: EmailStr
    id: str
    designation: Optional[str] = None
    client_name: Optional[str] = "jlens"

class UserResponse(BaseModel):
    id: UUID4
    email: EmailStr
    name: str
    designation: Optional[str]

    class Config:
        from_attributes = True

class UserComponentAccessCreate(BaseModel):
    user_id: UUID4
    component: str
    component_type: str
    source: Optional[str] = None

class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_private: Optional[bool] = True
    is_system_workspace: Optional[bool] = False
    user_id: Optional[UUID4] = None