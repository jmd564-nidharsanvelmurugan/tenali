from pydantic import BaseModel, UUID4, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from db.models import FileMetadataType, WorkspaceType

class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    preprompt: Optional[str] = None
    is_private: Optional[bool] = True

class WorkspaceOut(BaseModel):
    id: UUID4
    name: str
    description: Optional[str]
    pre_prompt: Optional[str] = None
    is_private: bool
    is_system_workspace: bool = False
    workspace_type: Optional[WorkspaceType] = WorkspaceType.own
    user_id: Optional[UUID4] = None
    owner_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ShareWorkspace(BaseModel):
    workspace_id: UUID4
    shared_with_email: str

class UnshareWorkspace(BaseModel):
    workspace_id: UUID4

class UpdatePrePrompt(BaseModel):
    pre_prompt: str

class FileMetadataOut(BaseModel):
    id: UUID4
    workspace_id: UUID4
    name: str
    link: Optional[str] = None
    full_path: str
    content_type: Optional[str] = None
    size: Optional[int] = None
    created_at: datetime
    type: Optional[FileMetadataType] = FileMetadataType.workspace
    
    # SharePoint specific fields
    sharepoint_link: Optional[str] = None
    last_modified_by_email: Optional[str] = None
    last_modified_by_name: Optional[str] = None
    last_modified_datetime: Optional[datetime] = None
    sharepoint_name: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class DbType(str, Enum):
    POSTGRESQL = "postgres"
    MONGODB = "mongodb"
    MYSQL = "mysql"

class TestMcpDb(BaseModel):
    db_uri: str = Field(..., description="The database URI")
    db_type: DbType = Field(..., description="The type of the database")

class AddMcp(BaseModel):
    name: str
    db_type: DbType
    db_uri: str
    workspace_id: UUID4
    description: Optional[str] = None
    read_only: bool = False

    # SSH Tunnel metadata
    ssh_tunnel: bool = False
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = 22
    ssh_username: Optional[str] = None
    ssh_local_port: Optional[int] = None
    ssh_remote_host: Optional[str] = "127.0.0.1"
    ssh_remote_port: Optional[int] = 5432

    # Secrets (unencrypted input)
    ssh_password: Optional[str] = None
    ssh_private_key: Optional[str] = None

class UpdateMcp(BaseModel):
    name: Optional[str] = None
    db_type: Optional[DbType] = None
    db_uri: Optional[str] = None
    description: Optional[str] = None
    read_only: Optional[bool] = None

    ssh_tunnel: Optional[bool] = None
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_username: Optional[str] = None
    ssh_local_port: Optional[int] = None
    ssh_remote_host: Optional[str] = None
    ssh_remote_port: Optional[int] = None

    ssh_password: Optional[str] = None
    ssh_private_key: Optional[str] = None


class FileListResponse(BaseModel):
    files: List[FileMetadataOut]
    total_count: int

class McpResponse(BaseModel):
    id: UUID4
    name: str
    db_type: DbType
    db_uri: str
    workspace_id: UUID4
    description: Optional[str]
    read_only: bool

    ssh_tunnel: bool
    ssh_host: Optional[str]
    ssh_port: Optional[int]
    ssh_username: Optional[str]
    ssh_local_port: Optional[int]
    ssh_remote_host: Optional[str]
    ssh_remote_port: Optional[int]

    class Config:
        from_attributes = True