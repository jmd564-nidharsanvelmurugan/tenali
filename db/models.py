from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Enum, ForeignKey, Text, JSON, Float
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum
import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from cryptography.fernet import Fernet, InvalidToken
import os

from dotenv import load_dotenv
load_dotenv()

Base = declarative_base()
# Load Fernet master key from environment
# Generate one with: Fernet.generate_key().decode()
MASTER_KEY = os.getenv("MASTER_KEY")
if not MASTER_KEY:
    fernet = None
else:
    fernet = Fernet(MASTER_KEY.encode())

# --- Enums ---

class UserRole(enum.Enum):
    admin = "admin"
    user = "user"

class ComponentType(enum.Enum):
    chat = "chat"
    proposal = "proposal"
    analytics = "analytics"
    marketplace = "marketplace"

class PermissionLevel(enum.Enum):
    read = "read"
    write = "write"

class McpDbType(enum.Enum):
    postgres = "postgres"
    mongo = "mongo"

class FileMetadataType(enum.Enum):
    workspace = "workspace"
    sharepoint = "sharepoint"

class IndexingStatus(enum.Enum):
    pending = "pending"
    indexed = "indexed"
    failed = "failed"
    dead_letter = "dead_letter"

class WorkspaceType(enum.Enum):
    system = "system"
    own = "own"
    shared = "shared"

class ChatType(enum.Enum):
    standalone = "standalone"
    document = "document"
    hybrid = "hybrid"
# --- Models ---

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)
    microsoft_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    designation = Column(String, nullable=True)
    client_name = Column(String, nullable=False)  # Required field, no default
    role = Column(Enum(UserRole), default=UserRole.user)
    has_given_feedback = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspaces = relationship("Workspace", back_populates="owner", cascade="all, delete")
    messages = relationship("Message", back_populates="user", cascade="all, delete")
    # file_metadata = relationship("FileMetadata", back_populates="user")
    conversations = relationship("Conversation", back_populates="owner", cascade="all, delete")
    access = relationship("UserComponentAccess", back_populates="user", cascade="all, delete")
    user_feedbacks = relationship("UserFeedback", back_populates="user", cascade="all, delete")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    pre_prompt = Column(Text, nullable=True)
    is_private = Column(Boolean, default=True)
    is_system_workspace = Column(Boolean, default=False)
    workspace_type = Column(Enum(WorkspaceType), default=WorkspaceType.own)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="workspaces")
    conversations = relationship("Conversation", back_populates="workspace", cascade="all, delete")
    file_metadata = relationship("FileMetadata", back_populates="workspace", cascade="all, delete")


class WorkspaceShare(Base):
    __tablename__ = "workspace_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shared_with_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="active")
    # TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
    # input_price_per_million = Column(Float, nullable=True)
    # output_price_per_million = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserComponentAccess(Base):
    __tablename__ = "user_component_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    component_id = Column(UUID(as_uuid=True), nullable=False)
    component_type = Column(String, nullable=False)  # 'model', 'feature', 'workspace'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="access")


class SystemWorkspaceTemplate(Base):
    __tablename__ = "system_workspace_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_key = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    pre_prompt = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Conversation(Base):
    __tablename__ = "conversation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    component_type = Column(Enum(ComponentType), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship("Message", back_populates="conversation", cascade="all, delete")
    workspace = relationship("Workspace", back_populates="conversations")
    owner = relationship("User", back_populates="conversations")


class Message(Base):    
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    content = Column(Text, nullable=False)
    role = Column(String(50), nullable=False)
    model_type = Column(String(50), nullable=True)
    chat_type = Column(Enum(ChatType), nullable=True)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="messages")
    conversation = relationship("Conversation", back_populates="messages")
    feedback = relationship("Feedback", back_populates="message", cascade="all, delete")

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    component = Column(Enum(ComponentType), nullable=False)
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="feedback")


class FileMetadata(Base):
    __tablename__ = "file_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum(FileMetadataType), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    full_path = Column(String(1024), nullable=False)
    link = Column(String(1024), nullable=True)
    uploaded_by_name = Column(String(255), nullable=True)
    uploaded_by_email = Column(String(255), nullable=True)
    # TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
    # indexing_status = Column(Enum(IndexingStatus), default=IndexingStatus.pending)
    # indexing_error = Column(Text, nullable=True)
    # indexing_attempts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    modified_at = Column(DateTime(timezone=True), nullable=True)

    workspace = relationship("Workspace", back_populates="file_metadata")
    # user = relationship("User", back_populates="file_metadata")

class QuestionType(enum.Enum):
    DROPDOWN = "DROPDOWN"
    RADIO = "RADIO"
    TEXT = "TEXT"

class QuestionCategory(enum.Enum):
    GENERAL = "GENERAL"
    BUSINESS_OFFERING = "BUSINESS_OFFERING"
    SOLUTION = "SOLUTION"
    REGION = "REGION"
    PROJECT_TYPE = "PROJECT_TYPE"
    COMMERCIAL_USE_CASE = "COMMERCIAL_USE_CASE"
    TECHNICAL_USE_CASE = "TECHNICAL_USE_CASE"
    BUSINESS_MODEL = "BUSINESS_MODEL"
    EXISTING_INFRA = "EXISTING_INFRA"
    PE_RELATIONSHIP = "PE_RELATIONSHIP"

# Model definition
class ProposalQuestions(Base):
    __tablename__ = "proposal_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    type = Column(Enum(QuestionType, name="question_type_enum"), nullable=False)
    options = Column(ARRAY(String(50)), nullable=True)  # stores list of strings (or null)
    category = Column(Enum(QuestionCategory, name="question_category_enum"), nullable=False)

class ProposalMetadata(Base):
    __tablename__ = "proposal_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    link = Column(String(500), nullable=False)

    # The properties field is a JSON object with optional keys mapping to lists of strings
    properties = Column(JSON, nullable=True)
    

class McpDbConfig(Base):
    __tablename__ = "mcp_db_meta"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    type = Column(Enum(McpDbType), nullable=False)
    db_uri = Column(String(1024), nullable=False)
    is_active = Column(Boolean, default=True)
    description = Column(String(1024), nullable=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    read_only = Column(Boolean, default=False)

    # System Prompt
    # system_prompt = Column(Text, nullable=True)

    # SSH Tunnel metadata (non-sensitive)
    ssh_tunnel = Column(Boolean, default=False)
    ssh_host = Column(String(255), nullable=True)
    ssh_port = Column(Integer, default=22)
    ssh_username = Column(String(255), nullable=True)
    ssh_local_port = Column(Integer, nullable=True)
    ssh_remote_host = Column(String(255), nullable=True, default="127.0.0.1")
    ssh_remote_port = Column(Integer, nullable=True, default=5432)

    # Encrypted secrets
    ssh_password_enc = Column(String(2048), nullable=True)
    ssh_private_key_enc = Column(String(8192), nullable=True)     

    # -----------------
    # Helper methods
    # -----------------
    def set_ssh_password(self, password: str):
        """Encrypt and store SSH password."""
        if password:
            if fernet is None:
                raise RuntimeError("MASTER_KEY not configured — cannot encrypt SSH password")
            self.ssh_password_enc = fernet.encrypt(password.encode()).decode()

    def get_ssh_password(self) -> str | None:
        """Decrypt SSH password."""
        if not self.ssh_password_enc:
            return None
        if fernet is None:
            raise RuntimeError("MASTER_KEY not configured — cannot decrypt SSH password")
        try:
            return fernet.decrypt(self.ssh_password_enc.encode()).decode()
        except InvalidToken:
            raise ValueError("Invalid encryption token for ssh_password_enc")

    def set_ssh_private_key(self, private_key: str):
        """Encrypt and store SSH private key."""
        if private_key:
            if fernet is None:
                raise RuntimeError("MASTER_KEY not configured — cannot encrypt SSH private key")
            self.ssh_private_key_enc = fernet.encrypt(private_key.encode()).decode()

    def get_ssh_private_key(self) -> str | None:
        """Decrypt SSH private key."""
        if not self.ssh_private_key_enc:
            return None
        if fernet is None:
            raise RuntimeError("MASTER_KEY not configured — cannot decrypt SSH private key")
        try:
            return fernet.decrypt(self.ssh_private_key_enc.encode()).decode()
        except InvalidToken:
            raise ValueError("Invalid encryption token for ssh_private_key_enc")


# TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
# class InfrastructureCost(Base):
#     __tablename__ = 'infrastructure_costs'
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     date = Column(DateTime(timezone=True), server_default=func.now())
#     service_name = Column(String(100), nullable=False)
#     environment = Column(String(50), default='production')
#     resource_name = Column(String(255), nullable=True)
#     cost_amount = Column(Float, nullable=False)
#     currency = Column(String(10), default='USD')
#     cost_type = Column(String(50), default='variable')
#     client_name = Column(String(100), nullable=True)
#     notes = Column(Text, nullable=True)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserAnalytics(Base):
    __tablename__ = "user_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    model_type = Column(String(100), nullable=True)
    chat_type = Column(String(50), nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    request_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="user_feedbacks")
