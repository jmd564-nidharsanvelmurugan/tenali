from pydantic import BaseModel, UUID4
from typing import Optional, List, Dict
 
class UserComponentAccessCreate(BaseModel):
    user_email: str
    component: str
    component_type: str
 
class UserComponentAccessUpdate(BaseModel):
    component: Optional[str]
    component_type: Optional[str]

class AccessToggle(BaseModel):
    component: str
    component_type: str
    enabled: bool

class BulkAccessUpdate(BaseModel):
    access_changes: List[AccessToggle]
 
class UserComponentAccessOut(BaseModel):
    id: UUID4
    user_id: UUID4
    component: str
    component_type: str
 
    class Config:
        from_attributes = True

class AvailableComponent(BaseModel):
    component: str
    component_type: str
    description: str

class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str
    designation: Optional[str] = None
    client_name: Optional[str] = "jlens"

class CreateFeatureRequest(BaseModel):
    name: str
    description: Optional[str] = None

class CreateModelRequest(BaseModel):
    name: str
    description: Optional[str] = None