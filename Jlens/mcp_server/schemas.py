from pydantic import BaseModel, EmailStr

class McpWorkspaceRequest(BaseModel):
    email: EmailStr
    access_key: str
