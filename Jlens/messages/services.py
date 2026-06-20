from sqlalchemy.orm import Session
import os
from uuid import UUID
from db.models import Message, Conversation, McpDbConfig, UserAnalytics
from .schemas import MessageCreate, MessageOut
from datetime import datetime
from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam
from dotenv import load_dotenv
import json
import httpx
from db.models import ChatType
from fastapi import HTTPException
import time
import requests
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
from openai.types.chat import ChatCompletionMessageParam
from typing import Optional, List, Tuple
from db.models import Workspace, User
from Jlens.lib.chat_client import ChatClient
import PyPDF2
import docx
import io
import re


def enhance_response_quality(response: str) -> str:
    """Post-process response for better business quality"""
    
    # Add business context markers
    if "recommendation" in response.lower() and not response.startswith("💡"):
        response = "💡 **Business Recommendation**\n\n" + response
    
    if "analysis" in response.lower() and not response.startswith("📊"):
        response = "📊 **Analysis Results**\n\n" + response
    
    # Format business lists
    response = format_business_lists(response)
    
    # Ensure professional structure
    response = ensure_professional_structure(response)
    
    return response

def format_business_lists(text: str) -> str:
    """Format business terms - preserve markdown formatting"""
    # Add emphasis to key business terms (only if not already bold)
    business_terms = ['ROI', 'KPI']
    for term in business_terms:
        pattern = r'(?<!\*\*)\b' + term + r'\b(?!\*\*)'
        text = re.sub(pattern, f'**{term}**', text)
    
    return text

def ensure_professional_structure(text: str) -> str:
    """Ensure response has professional structure"""
    lines = text.split('\n')
    
    # If response is long but has no structure, add it
    if len(lines) > 10 and not any(line.startswith('#') for line in lines):
        # Add executive summary if missing
        if not any('summary' in line.lower() for line in lines[:3]):
            text = "## Executive Summary\n\n" + text
    
    return text


# Token pricing per 1M tokens (USD) - hardcoded defaults
DEFAULT_TOKEN_PRICING = {
    "gpt-5.1-chat": {"input": 3.0, "output": 12.0},
    "gpt-4.1-mini": {"input": 0.15, "output": 0.6},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "DeepSeek-R1": {"input": 0.55, "output": 2.19},
    "model-router": {"input": 0.15, "output": 0.6},
    "default": {"input": 0.15, "output": 0.6}
}

def get_token_pricing(db: Session = None) -> dict:
    """Get token pricing from DB (AIModel table) with fallback to hardcoded defaults"""
    pricing = dict(DEFAULT_TOKEN_PRICING)
    if db:
        try:
            from db.models import AIModel
            models = db.query(AIModel).filter(AIModel.status == "active", AIModel.input_price_per_million.isnot(None)).all()
            for m in models:
                pricing[m.model_id] = {"input": m.input_price_per_million, "output": m.output_price_per_million or 0.0}
        except Exception:
            pass
    return pricing

# Keep backward-compatible reference
TOKEN_PRICING = DEFAULT_TOKEN_PRICING

def calculate_cost(model_type: str, input_tokens: int, output_tokens: int, db: Session = None) -> float:
    """Calculate estimated cost based on token usage"""
    pricing_table = get_token_pricing(db) if db else DEFAULT_TOKEN_PRICING
    pricing = pricing_table.get(model_type, pricing_table.get("default", DEFAULT_TOKEN_PRICING["default"]))
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)

def extract_text_from_file_content(file_content: bytes, filename: str) -> str:
    """Extract text content from different file types for JLens temporary processing"""
    try:
        file_extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        if file_extension == 'pdf':
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text[:50000]  # Increased limit to 50k chars for better analysis
        elif file_extension in ['docx', 'doc']:
            docx_file = io.BytesIO(file_content)
            doc = docx.Document(docx_file)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text[:50000]  # Increased limit to 50k chars for better analysis
        elif file_extension == 'txt':
            return file_content.decode('utf-8', errors='ignore')[:50000]  # Increased limit
        else:
            return file_content.decode('utf-8', errors='ignore')[:50000]  # Increased limit
    except Exception as e:
        print(f"Error extracting text from {filename}: {str(e)}")
        return f"[Could not extract text from {filename}]"

def process_jlens_files(files) -> tuple[str, list]:
    """Process files for JLens workspace - extract text and return references"""
    if not files:
        return "", []
    
    file_context = "\n\n=== UPLOADED FILES FOR ANALYSIS ===\n"
    file_references = []
    
    for file in files:
        try:
            file_content = file.file.read()
            text_content = extract_text_from_file_content(file_content, file.filename)
            
            file_context += f"\n--- File: {file.filename} ---\n"
            file_context += text_content
            file_context += "\n" + "="*50 + "\n"
            
            # Add file reference for citations
            file_references.append({
                "id": f"jlens-file-{len(file_references)}",
                "title": file.filename,
                "content": text_content[:500] + "..." if len(text_content) > 500 else text_content,
                "filepath": file.filename,
                "file_link": f"#uploaded-file-{file.filename}",
                "source": "JLens Upload"
            })
            
        except Exception as e:
            file_context += f"\n--- File: {file.filename} ---\n"
            file_context += f"[Error processing file: {str(e)}]\n"
            file_context += "="*50 + "\n"
    
    return file_context, file_references

def get_search_index_for_workspace(workspace) -> str:
    """Get the appropriate search index based on workspace name and type"""
    from db.models import WorkspaceType
    
    # Jman Sales workspace always uses SharePoint sales index
    if workspace.name == "Jman Sales":
        return "tenaliaiaz-sharepoint-sales-index"
    
    if workspace.name == "Nexus":
        return "nexus-ms"
    
    if workspace.name in ("AISOW", "Demo"):
        if workspace.name == "Demo":
            return "tenaliaz-demo-index"
        return "tenaliaz-aisow-index"
    
    # System workspaces use dedicated indexes
    if workspace.workspace_type == WorkspaceType.system:
        # Add other system workspace indexes here
        return "workspaces"  # fallback
    
    # Own and shared workspaces use the user workspace index
    return "tenaliaiaz-jlens-user-workspace"

def get_fields_mapping_for_workspace(workspace) -> dict:
    """Get field mapping configuration based on workspace name and type"""
    from db.models import WorkspaceType
    
    # Jman Sales workspace always uses SharePoint fields
    if workspace.name == "Jman Sales":
        return {
            "contentFields": ["chunk"],
            "titleField": "title",
            "urlField": "sharepoint_url", 
            "filepathField": "sharepoint_name",
            "vectorFields": ["text_vector"]
        }
    
    if workspace.name == "Nexus":
        return {
            "contentFields": ["chunk"],
            "titleField": "title",
            "vectorFields": ["text_vector"]
        }
    
    if workspace.name in ("AISOW", "Demo"):
        return {
            "contentFields": ["chunk"],
            "titleField": "title",
            "urlField": "sharepoint_url", 
            "filepathField": "sharepoint_name",
            "vectorFields": ["text_vector"]
        }
    
    if workspace.workspace_type == WorkspaceType.system:
        # Legacy system workspace mapping
        return {
            "contentFields": AZURE_SEARCH_CONTENT_COLUMNS.split(",") if AZURE_SEARCH_CONTENT_COLUMNS else [],
            "titleField": AZURE_SEARCH_TITLE_COLUMN,
            "urlField": AZURE_SEARCH_URL_COLUMN,
            "filepathField": AZURE_SEARCH_FILENAME_COLUMN,
            "vectorFields": AZURE_SEARCH_VECTOR_COLUMNS.split(",") if AZURE_SEARCH_VECTOR_COLUMNS else [],
        }
    
    # User workspace mapping
    return {
        "contentFields": ["chunk"],
        "titleField": "title",
        "urlField": "file_link",
        "filepathField": "file_name", 
        "vectorFields": ["text_vector"]
    }

def get_search_query_type_for_workspace(workspace) -> str:
    """Get query type based on workspace"""
    from db.models import WorkspaceType
    
    # Jman Sales workspace always uses semantic search
    if workspace.name == "Jman Sales":
        return "semantic"
    elif workspace.name == "Nexus":
        return "semantic"
    elif workspace.name in ("AISOW", "Demo"):
        return "semantic"
    elif workspace.workspace_type in [WorkspaceType.own, WorkspaceType.shared]:
        return "semantic"
    
    return AZURE_SEARCH_QUERY_TYPE

def get_semantic_config_for_workspace(workspace) -> str:
    """Get semantic configuration based on workspace name and type"""
    from db.models import WorkspaceType
    
    # Jman Sales workspace uses SharePoint semantic config
    if workspace.name == "Jman Sales":
        return "tenaliaiaz-sharepoint-sales-index-semantic-configuration"
    elif workspace.name == "Nexus":
        return "nexus-ms-semantic-configuration"
    elif workspace.name in ("AISOW", "Demo"):
        return "semantic-config"
    elif workspace.workspace_type in [WorkspaceType.own, WorkspaceType.shared]:
        return "tenaliaiaz-jlens-user-workspace-semantic-configuration"
    
    return AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG

def get_scoring_profile_for_workspace(workspace) -> str:
    """Get scoring profile based on workspace name and type"""
    from db.models import WorkspaceType
    
    # Jman Sales workspace uses hybrid boost
    if workspace.name == "Jman Sales":
        return "hybridBoost"
    elif workspace.name == "Nexus":
        return "hybridBoost"
    elif workspace.name in ("AISOW", "Demo"):
        return "hybridBoost"
    elif workspace.workspace_type in [WorkspaceType.own, WorkspaceType.shared]:
        return "hybridBoost"  # Now configured as default in user workspace index
    
    return ""  # No scoring profile for other workspaces

def get_search_filter_for_workspace(workspace, user_id: str) -> str:
    """Get search filter based on workspace name and type"""
    from db.models import WorkspaceType
    
    # Jman Sales workspace doesn't need user filtering (system-wide data)
    if workspace.name == "Jman Sales":
        return ""
    elif workspace.name == "Nexus":
        return ""
    elif workspace.name in ("AISOW", "Demo"):
        return ""
    
    # System workspaces don't need user filtering
    if workspace.workspace_type == WorkspaceType.system:
        return ""
    
    # User workspaces need filtering by workspace_id only
    return f"workspace_id eq '{workspace.id}'"

def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough approximation: 1 token ≈ 4 characters)"""
    return max(1, len(text) // 4)

def track_analytics(db: Session, user_id: UUID, workspace_id: UUID, model_type: str, 
                    chat_type: str, input_tokens: int, output_tokens: int):
    """Track user analytics for each request"""
    total_tokens = input_tokens + output_tokens
    estimated_cost = calculate_cost(model_type, input_tokens, output_tokens)
    
    analytics = UserAnalytics(
        user_id=user_id,
        workspace_id=workspace_id,
        model_type=model_type,
        chat_type=chat_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost
    )
    db.add(analytics)
    db.commit()


# import pika

load_dotenv()
#RabbitMQ configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
#OpenAI configuration
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL_NAME_1")
AZURE_OPENAI_RESOURCE = os.getenv("AZURE_OPENAI_RESOURCE")
AZURE_OPENAI_PREVIEW_API_VERSION = os.getenv("AZURE_OPENAI_PREVIEW_API_VERSION", "2024-05-01-preview")

#Azure Search configuration
AZURE_SEARCH_QUERY_TYPE = os.getenv("AZURE_SEARCH_QUERY_TYPE", "semantic")
AZURE_SEARCH_USE_SEMANTIC_SEARCH = os.getenv("AZURE_SEARCH_USE_SEMANTIC_SEARCH", "true")
AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG = os.getenv("AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG", "")
AZURE_OPENAI_TEMPERATURE = os.getenv("AZURE_OPENAI_TEMPERATURE", "0.7")
AZURE_OPENAI_MAX_TOKENS = os.getenv("AZURE_OPENAI_MAX_TOKENS", "1000")
AZURE_OPENAI_TOP_P = os.getenv("AZURE_OPENAI_TOP_P", "1.0")
AZURE_OPENAI_STOP_SEQUENCE = os.getenv("AZURE_OPENAI_STOP_SEQUENCE", "")
AZURE_SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_CONTENT_COLUMNS = os.getenv("AZURE_SEARCH_CONTENT_COLUMNS", "")
AZURE_SEARCH_TITLE_COLUMN = os.getenv("AZURE_SEARCH_TITLE_COLUMN", "")
AZURE_SEARCH_URL_COLUMN = os.getenv("AZURE_SEARCH_URL_COLUMN", "")
AZURE_SEARCH_FILENAME_COLUMN = os.getenv("AZURE_SEARCH_FILENAME_COLUMN", "")
AZURE_SEARCH_VECTOR_COLUMNS = os.getenv("AZURE_SEARCH_VECTOR_COLUMNS", "")
AZURE_SEARCH_TOP_K = int(os.getenv("AZURE_SEARCH_TOP_K", 5))
AZURE_OPENAI_SYSTEM_MESSAGE = os.getenv("AZURE_OPENAI_SYSTEM_MESSAGE", "You are a helpful assistant.")
AZURE_OPENAI_EMBEDDING_ENDPOINT = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
AZURE_OPENAI_EMBEDDING_KEY = os.getenv("AZURE_OPENAI_EMBEDDING_KEY")
AZURE_SEARCH_STRICTNESS = os.getenv("AZURE_SEARCH_STRICTNESS", "0")

def load_common_preprompt() -> str:
    """Load common pre-prompt structure and formatting rules"""
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../", "common_preprompt.txt"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            common_prompt = f.read().strip()
        current_date = datetime.today().strftime("%d/%m/%Y")
        common_prompt = common_prompt.replace("{{CURRENT_DATE}}", current_date)
        return common_prompt
    except Exception:
        return ""

def combine_prompts(workspace_prompt: str = None, user_name: str = None) -> str:
    """Combine common pre-prompt with workspace-specific prompt"""
    common_prompt = load_common_preprompt()
    
    if workspace_prompt:
        # Combine workspace prompt with common formatting rules
        combined = f"{workspace_prompt}\n\n{common_prompt}"
    else:
        # Use default with common rules
        combined = f"You are an AI assistant helping users through the Jlens AI Platform at JMAN Group.\n\n{common_prompt}"
    
    # Add user context if available
    if user_name:
        combined = f"Current user: {user_name}\n\n{combined}"
    
    return combined

def load_system_message(filename: str = "context.txt") -> str:
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../", filename))
    try:
        with open(path, "r", encoding="utf-8") as f:
            system_message = f.read().strip()
        current_date = datetime.today().strftime("%d/%m/%Y")
        system_message = system_message.replace("{{CURRENT_DATE}}", current_date)
        return system_message
    except Exception:
        return "You are a helpful assistant."

# Load the original system message for document chat
AZURE_OPENAI_SYSTEM_MESSAGE = (
    (AZURE_OPENAI_SYSTEM_MESSAGE + "\n" if AZURE_OPENAI_SYSTEM_MESSAGE else "")
    + load_system_message()
)

def get_model_specific_system_message(model_type: str, user_name: str = None) -> str:
    """Generate comprehensive system message for standalone chat"""
    
    system_msg = f"""You are an AI assistant helping users through the Jlens AI Platform at JMAN Group.

## 🤖 Your Identity
- **Platform**: Jlens Enterprise AI Platform
- **Organization**: JMAN Group
- **Current User**: {user_name or "User"}
- **Mode**: Standalone Chat (General Assistance)
- **Date**: {datetime.now().strftime('%d/%m/%Y')}

## Your Role
- Provide helpful, accurate, and professional assistance
- Maintain a conversational and engaging tone
- Ask clarifying questions when needed
- Offer practical solutions and actionable advice

## Response Guidelines
- Be concise yet thorough in your explanations
- Use clear, simple language appropriate for the user
- Structure responses with headers and bullet points when helpful
- Provide examples or step-by-step guidance for complex topics
- Acknowledge when you don't know something or need more information

## Communication Style
- Start responses by addressing the user by name: "Hi {user_name or "there"},"
- Be friendly and approachable while remaining professional
- Use formatting (bold, lists, etc.) to improve readability
- Tailor your response complexity to match the user's question

Remember: Focus on being genuinely helpful and creating an interactive conversation that serves {user_name or "the user"}'s needs."""
    
    return system_msg

def get_jlens_system_message(user_name: str = None, file_context: str = "") -> str:
    """Generate enhanced JLens-specific system message for superior business responses"""
    
    system_msg = f"""You are JLens AI Assistant - JMAN Group's premium business AI platform.

## Your Enhanced Role
- **Primary Function**: Provide exceptional business-focused AI assistance
- **Expertise**: Business analysis, strategic insights, document processing, and professional communication
- **Standards**: Deliver structured, actionable, and high-value responses

## Business Communication Excellence
- **Structure**: Use clear headings, bullet points, and professional formatting
- **Tone**: Professional yet approachable, suitable for executive-level communication
- **Focus**: Emphasize business impact, ROI, and actionable recommendations
- **Quality**: Provide comprehensive yet concise responses with clear next steps

## Response Enhancement Guidelines
1. **Start with Key Insights**: Lead with the most important information
2. **Use Business Structure**: 
   - Executive Summary for complex topics
   - Key Findings with bullet points
   - Business Impact assessment
   - Clear Recommendations with next steps
3. **Professional Formatting**:
   - Use **bold** for critical points
   - Use bullet points (•) for lists
   - Use numbered lists for processes
   - Include relevant business metrics when applicable

## JMAN Group Context
- **Industry**: Technology consulting and business solutions
- **Focus**: Enterprise-grade services, digital transformation, strategic consulting
- **Values**: Innovation, excellence, client success, professional growth
- **Terminology**: Use business-appropriate language (ROI, KPIs, efficiency, strategy, optimization)

## Enhanced File Processing
- Files processed temporarily with advanced analysis capabilities
- Extract business insights, key metrics, and actionable data
- Provide structured summaries with executive-level recommendations
- Focus on business value and strategic implications

## 👤 Current Session
- **User**: {user_name or "Business User"}
- **Date**: {datetime.now().strftime('%B %d, %Y')}
- **Platform**: JLens Enterprise AI Platform
- **Environment**: JMAN Group Secure Network

{file_context}

## Quality Standards
- Ensure responses are actionable and business-relevant
- Include specific recommendations with clear next steps
- Use professional formatting and structure
- Focus on business value and practical implementation
- Maintain executive-level communication standards

Remember: You represent JMAN Group's commitment to excellence. Every response should reflect professional quality and business acumen."""
    
    return system_msg

httpx_client = httpx.Client(
    base_url=AZURE_OPENAI_ENDPOINT,
    headers={"api-key": AZURE_OPENAI_KEY},
    timeout=60.0,
)

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-05-01-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    http_client=httpx_client,
)

def create_message(db: Session, user_id: UUID, msg_data: MessageCreate) -> Message:
    # if msg_data.conversation_id:
    #     # Use existing conversation
    #     conversation = db.query(Conversation).filter_by(id=msg_data.conversation_id).first()
    #     if not conversation:
    #         raise HTTPException(status_code=404, detail="Conversation not found")
    # else:
    #     if not msg_data.component_type:
    #         raise HTTPException(status_code=400, detail="Conversation type is required for first message")
    #     conversation = Conversation(
    #         title="Untitled",
    #         user_id=user_id,
    #         workspace_id=msg_data.workspace_id,
    #         component_type=msg_data.component_type
    #     )
    #     db.add(conversation)
    #     db.commit()
    #     db.refresh(conversation)
    conversation = db.query(Conversation).filter_by(id=msg_data.conversation_id).first()

    msg = Message(
        conversation_id=conversation.id,
        workspace_id=msg_data.workspace_id,
        user_id=user_id,
        content=msg_data.content,
        role=msg_data.role,
        model_type=msg_data.model_type,
        chat_type=ChatType(msg_data.chat_type) if msg_data.chat_type else ChatType.standalone,
        input_tokens=msg_data.input_tokens,
        output_tokens=msg_data.output_tokens,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    
    # Track analytics for assistant messages
    if msg.role == "assistant":
        # Ensure we have token counts (use estimates if not provided)
        input_tokens = msg.input_tokens if msg.input_tokens > 0 else estimate_tokens(msg.content)
        output_tokens = msg.output_tokens if msg.output_tokens > 0 else estimate_tokens(msg.content)
        
        track_analytics(
            db, user_id, msg_data.workspace_id, 
            msg_data.model_type or "unknown",
            msg_data.chat_type.value if hasattr(msg_data.chat_type, 'value') else str(msg_data.chat_type or "standalone"),
            input_tokens, output_tokens
        )

    return msg

def create_model_message(
    db: Session,
    user_id: UUID,
    workspace_id: UUID,
    conversation_id: UUID,
    content: str,
    model_type: str,
    chat_type: ChatType,
    role: str = "assistant",
    input_tokens: int = 0,
    output_tokens: int = 0
) -> Message:
    # Estimate tokens if not provided
    if input_tokens == 0 and output_tokens == 0 and role == "assistant":
        output_tokens = estimate_tokens(content)
    
    msg = Message(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        user_id=user_id,
        content=content,
        role=role,
        model_type=model_type,
        chat_type=ChatType(chat_type),
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    
    # Track analytics for assistant messages
    if role == "assistant":
        track_analytics(
            db, user_id, workspace_id, 
            model_type or "unknown",
            chat_type.value if hasattr(chat_type, 'value') else str(chat_type),
            input_tokens, output_tokens
        )
    
    return msg
    return msg

def generate_title(first_message: dict, model_type: str = None, assistant_response: str = None) -> str:
    """
    Generate a short title (≤ 4 words) from the first user message and assistant response.
    If the message is generic or vague (like hi, hello, ok), return 'New Conversation'.
    """
    if assistant_response:
        # Generate title from both question and answer
        title_prompt = (
            "Based on the user's question and assistant's response, create a concise conversation title (4 words or fewer).\n"
            "Rules:\n"
            "- If it's a generic greeting, respond with JSON: {\"title\": \"generic\"}.\n"
            "- Otherwise, summarize the conversation topic into a short title without punctuation, and return in JSON: {\"title\": \"...\"}.\n"
            f"User Question: {first_message['content']}\n"
            f"Assistant Response: {assistant_response[:200]}"
        )
    else:
        # Fallback: Generate from question only
        title_prompt = (
            "Analyze the following message:\n"
            "- If it is a generic greeting or very short/vague (like hi, hello, hey, ok, yes, etc.), respond only with JSON: {\"title\": \"generic\"}.\n"
            "- Otherwise, summarize the message into a short title (4 words or fewer) without punctuation or quotes, and return in JSON: {\"title\": \"...\"}.\n"
            f"Message: {first_message['content']}"
        )

    # Use the selected model for title generation
    deployment_model = model_type or AZURE_OPENAI_DEPLOYMENT

    try:
        response = client.chat.completions.create(
            model=deployment_model,
            messages=[
                {"role": "system", "content": "You are an assistant that creates concise conversation titles."},
                {"role": "user", "content": title_prompt}
            ],
            temperature=0.7,
            max_completion_tokens=20,
        )
        content = response.choices[0].message.content.strip()
        
        try:
            title = json.loads(content).get("title", "Untitled")
        except json.JSONDecodeError:
            # If not valid JSON, use the content directly as title
            title = content.replace('"', '').strip()
            # Limit to 4 words
            words = title.split()[:4]
            title = " ".join(words)

        if title.lower() == "generic":
            return "New Conversation"
        title = title[:1].upper() + title[1:]
        return title if title else "New Conversation"

    except Exception as e:
        # Create a simple title from the first few words of the message
        try:
            words = first_message.get("content", "").split()[:3]
            return " ".join(words) if words else "New Conversation"
        except:
            return "New Conversation"
    
def get_mcp_by_workspace_id(db: Session, workspace_id: UUID):
    return ( 
        db.query(McpDbConfig).filter(McpDbConfig.workspace_id == workspace_id, McpDbConfig.is_active).all()
    )
    
def get_messages_by_conversation(db: Session, conversation_id: UUID):
    return (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at)
        .all()
    )

async def conversation_with_data(db: Session, user_msg: MessageOut, user_id: UUID, message: MessageCreate):
    messages_db = get_messages_by_conversation(db, user_msg.conversation_id)
    messages: List[dict] = [
        {"role": msg.role, "content": msg.content} for msg in messages_db if msg.role != "tool"
    ]
 
    # Get user information for personalized responses
    user = db.query(User).filter(User.id == user_id).first()
    user_name = user.name if user else None
    
    current_workspace = db.query(Workspace).filter_by(id=message.workspace_id).first()

    # --- AISOW: LangChain Agentic RAG ---
    if current_workspace and current_workspace.name in ("AISOW", "Demo"):
        from AISOW.agent import run_aisow_agent
        from AISOW.tools import set_index
        import asyncio, json as _json

        # Set the correct search index for this workspace
        if current_workspace.name == "Demo":
            set_index("tenaliaz-demo-index")
        else:
            set_index("tenaliaz-aisow-index")

        async def aisow_stream():
            full_response = ""
            citations_payload = None
            try:
                async for token in run_aisow_agent(message.content, messages):
                    if token.startswith("CITATIONS_PAYLOAD:"):
                        citations_payload = _json.loads(token[len("CITATIONS_PAYLOAD:"):])
                        continue
                    full_response += token
                    yield f"data: {_json.dumps({'token': token})}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {_json.dumps({'token': 'Request timed out after 3 minutes. Please try a simpler question.'})}\n\n"
                return
            except Exception as e:
                print(f"AISOW agent error: {e}")
                yield f"data: {_json.dumps({'token': f'Error: {str(e)}'})}\n\n"
                return

            assistant_msg = create_model_message(
                db, user_id, message.workspace_id, message.conversation_id,
                full_response, message.model_type or AZURE_OPENAI_DEPLOYMENT,
                message.chat_type or ChatType.document
            )

            if citations_payload:
                citations_payload["message_id"] = str(assistant_msg.id)
                citations_payload["citations"] = citations_payload["citations"][:20]
                yield f"data: {_json.dumps(citations_payload)}\n\n"
                create_model_message(
                    db=db, user_id=user_id, workspace_id=message.workspace_id,
                    conversation_id=message.conversation_id,
                    content=_json.dumps(citations_payload["citations"]),
                    model_type=message.model_type, chat_type=ChatType(message.chat_type), role="tool"
                )

        return StreamingResponse(aisow_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
    # --- end AISOW ---
    
    # Get all users with access to this workspace (owner + shared users)
    from db.models import WorkspaceShare
    workspace_users = []
    
    # Add owner email if workspace has an owner (system workspaces have no owner)
    if current_workspace and current_workspace.owner:
        workspace_users.append(current_workspace.owner.email)
    
    shared_users = db.query(User).join(WorkspaceShare, WorkspaceShare.shared_with_id == User.id).filter(
        WorkspaceShare.workspace_id == message.workspace_id
    ).all()
    workspace_users.extend([user.email for user in shared_users])
    
    # Build filter to search across all workspace users' documents
    group_filters = [f"group_name eq '{current_workspace.name}-{email}'" for email in workspace_users]
    group_filter = " or ".join(group_filters)
 
    async def token_stream():
        # Use a valid model deployment for document chat
        # Map user selection to valid Azure deployments
        model_mapping = {
            "gpt-5.1-chat": "gpt-4.1-mini",
            "gpt-5": "gpt-4.1-mini", 
            "DeepSeek-R1": "gpt-4.1-mini",  # Fallback for document chat
            "mistral": "gpt-4.1-mini",
            "Llama": "gpt-4.1-mini"
        }
        
        selected_model = message.model_type or AZURE_OPENAI_DEPLOYMENT
        model_deployment = model_mapping.get(selected_model, selected_model)
        
        # Claude uses Anthropic API, Grok uses OpenAI v1, others use extensions
        if "claude" in selected_model.lower():
            # Anthropic API endpoint
            url = f"{AZURE_OPENAI_ENDPOINT.replace('/openai/', '/anthropic/')}/v1/messages"
            headers = {
                "x-api-key": AZURE_OPENAI_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        elif "grok" in selected_model.lower():
            # OpenAI v1 endpoint for Grok
            url = f"{AZURE_OPENAI_ENDPOINT}/v1/chat/completions"
            headers = {
                "api-key": AZURE_OPENAI_KEY,
                "Content-Type": "application/json"
            }
        else:
            # Extensions endpoint for other models
            url = (
                f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{model_deployment}/extensions/chat/completions"
                f"?api-version=2023-06-01-preview"
            )
            headers = {
                "api-key": AZURE_OPENAI_KEY,
                "Content-Type": "application/json"
            }
 
        # Build request body based on model type
        if "claude" in selected_model.lower():
            # Anthropic format
            body = {
                "model": model_deployment,
                "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"],
                "max_tokens": int(AZURE_OPENAI_MAX_TOKENS),
                "temperature": float(AZURE_OPENAI_TEMPERATURE),
                "stream": True
            }
            # Add system message separately for Claude
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
            if system_msg:
                body["system"] = system_msg
        else:
            # OpenAI format
            body = {
                "messages": messages,
                "temperature": float(AZURE_OPENAI_TEMPERATURE),
                "max_tokens": int(AZURE_OPENAI_MAX_TOKENS),
                "top_p": float(AZURE_OPENAI_TOP_P),
                "stop": None,
                "stream": True
            }
            
            # Only add dataSources for extensions endpoint (not Grok or Claude)
            if "grok" not in selected_model.lower():
                search_index = get_search_index_for_workspace(current_workspace)
                fields_mapping = get_fields_mapping_for_workspace(current_workspace)
                search_filter = get_search_filter_for_workspace(current_workspace, str(user_id))
                
                # Create personalized role information with common formatting
                if message.pre_prompt:
                    role_info = combine_prompts(message.pre_prompt, user_name)
                else:
                    role_info = combine_prompts(AZURE_OPENAI_SYSTEM_MESSAGE, user_name)
                
                # Document search configured
                
                body["dataSources"] = [
                {
                    "type": "AzureCognitiveSearch",
                    "parameters": {
                        "endpoint": f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
                        "key": AZURE_SEARCH_KEY,
                        "indexName": search_index,
                        "fieldsMapping": fields_mapping,
                        "inScope": True if message.chat_type == ChatType.document else False,
                        "topNDocuments": 20 if current_workspace.name in ("AISOW", "Demo") else 5,
                        "queryType": get_search_query_type_for_workspace(current_workspace),
                        "semanticConfiguration": get_semantic_config_for_workspace(current_workspace) or None,
                        "scoringProfile": get_scoring_profile_for_workspace(current_workspace) or None,
                        "roleInformation": role_info,
                        "embeddingEndpoint": AZURE_OPENAI_ENDPOINT,
                        "embeddingKey": AZURE_OPENAI_KEY,
                        "filter": search_filter,
                    }
                }
            ]
 
        collected_response = ""
        tool_response = ""
        input_tokens = 0
        output_tokens = 0
 
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
              async with client.stream("POST", url, headers=headers, json=body) as response:
                response.raise_for_status()
 
                async for raw_line in response.aiter_lines():
                    if not raw_line:
                        continue
 
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    
 
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
 
                    content = line[5:].strip()
                    
 
                    if content == "[DONE]":
                        break
 
                    try:
                        delta = json.loads(content)
                        
                        # Extract usage information if available
                        if "usage" in delta:
                            usage = delta["usage"]
                            input_tokens = usage.get("prompt_tokens", 0)
                            output_tokens = usage.get("completion_tokens", 0)
                        
                        # Handle Claude's Anthropic API format
                        if "claude" in selected_model.lower():
                            event_type = delta.get("type")
                            if event_type == "content_block_delta":
                                text_delta = delta.get("delta", {}).get("text", "")
                                if text_delta:
                                    collected_response += text_delta
                                    to_yield = json.dumps({"content": text_delta})
                                    yield f"data: {to_yield}\n\n"
                            continue
                        
                        # Handle OpenAI format (Grok and others)
                        choice = delta.get("choices", [{}])[0]
                        stream_messages = choice.get("messages", [])
 
                        for msg in stream_messages:
                            inner_delta = msg.get("delta", {})
                            role = inner_delta.get("role", "")
                            token = inner_delta.get("content", "")
 
                            if role == "tool":
                                
                                tool_response += token
                            elif token and token != "[DONE]":
                                
                                collected_response += token
                                to_yield = json.dumps({"token": token})
                                yield f"data: {to_yield}\n\n"
                    except Exception as e:
                        continue
 
            # Estimate tokens if not provided by API
            if input_tokens == 0:
                # Estimate input tokens from messages
                input_text = " ".join([m.get("content", "") for m in messages])
                input_tokens = estimate_tokens(input_text)
            
            if output_tokens == 0:
                # Estimate output tokens from response
                output_tokens = estimate_tokens(collected_response)
 
            # Save assistant message
            if collected_response.strip():
                # Append model icon and name to the response
                model_signature = f"\n\n[MODEL:{message.model_type}]"
                collected_response += model_signature
                
                # Send the model signature as final tokens
                for char in model_signature:
                    to_yield = json.dumps({"token": char})
                    yield f"data: {to_yield}\n\n"
                
                # Save the message with token counts
                assistant_msg = create_message(
                    db=db,
                    user_id=user_id,
                    msg_data=MessageCreate(
                        conversation_id=user_msg.conversation_id,
                        workspace_id=message.workspace_id,
                        content=collected_response,
                        role="assistant",
                        model_type=message.model_type,
                        chat_type=message.chat_type,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens
                    )
                )
                
                # Generate title in background (don't block stream)
                conversation = db.query(Conversation).filter_by(id=user_msg.conversation_id).first()
                msg_count = db.query(Message).filter_by(conversation_id=user_msg.conversation_id).count()
                if msg_count == 2 and conversation and conversation.title == "New Conversation":
                    first_user_msg = db.query(Message).filter_by(
                        conversation_id=user_msg.conversation_id, 
                        role="user"
                    ).first()
                    if first_user_msg:
                        import asyncio, concurrent.futures
                        conv_id = user_msg.conversation_id
                        first_content = first_user_msg.content
                        model = message.model_type
                        resp_text = collected_response
                        def _bg_title():
                            try:
                                new_title = generate_title(
                                    {"role": "user", "content": first_content},
                                    model, resp_text
                                )
                                if new_title != "New Conversation":
                                    conv = db.query(Conversation).filter_by(id=conv_id).first()
                                    if conv:
                                        conv.title = new_title
                                        db.commit()
                            except Exception:
                                pass
                        loop = asyncio.get_event_loop()
                        loop.run_in_executor(None, _bg_title)
 
            # Save tool (citation) message and include citations in response
            if tool_response.strip():
                # Get search results for URL mapping
                search_results = []
                if message.chat_type == "document":
                    from Jlens.lib.azure_search_service import search_documents
                    try:
                        search_results = search_documents(message.content, current_workspace.name, limit=10)
                    except Exception as e:
                        print(f"Error getting search results for URL mapping: {e}")
                
                # Create URL mapping from search results
                url_mapping = {}
                for result in search_results:
                    title = result.get('title', '')
                    # Use correct field names based on workspace
                    if current_workspace.name == "Jman Sales":
                        url = result.get('sharepoint_url', '')  # tenaliaiaz-sharepoint-sales-index
                    else:
                        url = result.get('file_link', '')       # tenaliaiaz-jlens-user-workspace
                    
                    if title and url:
                        url_mapping[title] = url
                
                try:
                    parsed_citations = json.loads(tool_response)
                    
                    # Handle different citation formats
                    citations_list = []
                    if isinstance(parsed_citations, list):
                        citations_list = parsed_citations
                    elif isinstance(parsed_citations, dict) and 'citations' in parsed_citations:
                        citations_list = parsed_citations['citations']
                    
                    if citations_list:
                        # Check if LLM response actually references documents
                        import re
                        doc_references = re.findall(r'\[doc\d+\]', collected_response)
                        
                        # Only show citations if LLM response contains document references
                        if doc_references:
                            # Filter and format citations
                            relevant_citations = []
                            for citation in citations_list:
                                if isinstance(citation, dict):
                                    content = citation.get('content', '').strip()
                                    title = citation.get('title', '').strip()
                                    
                                    if content and len(content) > 50 and title:
                                        relevant_citations.append({
                                            'title': title,
                                            'content': content[:1500] + '...' if len(content) > 1500 else content,
                                            'url': citation.get('url', ''),
                                            'filepath': citation.get('filepath', ''),
                                            'chunk_id': citation.get('chunk_id', ''),
                                        })
                            
                            if relevant_citations:
                                # Send structured citations for UI
                                citations_data = json.dumps({
                                    "type": "citations_ready",
                                    "message_id": str(user_msg.id),
                                    "citations": relevant_citations
                                })
                                yield f"data: {citations_data}\n\n"
                                
                                # Save citations to database
                                create_model_message(
                                    db=db,
                                    user_id=user_id,
                                    workspace_id=message.workspace_id,
                                    conversation_id=user_msg.conversation_id,
                                    content=json.dumps(relevant_citations, indent=2),
                                    model_type=message.model_type,
                                    chat_type=ChatType(message.chat_type),
                                    role="tool"
                                )
                    
                except Exception as e:
                    pass
            
            # Send final done signal
            yield f"data: {json.dumps({'token': '[DONE]'})}\n\n"
 
        except httpx.HTTPStatusError as e:
            yield f"data: {json.dumps({'error': f'HTTP {e.response.status_code}'})}\n\n"
            raise HTTPException(status_code=e.response.status_code, detail=f"Model API error: {e.response.status_code}")
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            raise HTTPException(status_code=500, detail=f"Failed to stream model response: {str(e)}")
 
    return StreamingResponse(
        token_stream(), 
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )
 
 
async def conversation_without_data(db: Session, user_msg: MessageOut, user_id: UUID, message: MessageCreate, files=None):
    messages_db = get_messages_by_conversation(db, user_msg.conversation_id)

    # Get user information
    user = db.query(User).filter(User.id == user_id).first()
    user_name = user.name if user else None
    
    # Get workspace information
    workspace = db.query(Workspace).filter(Workspace.id == message.workspace_id).first()
    
    # Check if this is JLens workspace
    if workspace and workspace.name == "JLens":
        # Process files temporarily for JLens
        file_context = ""
        if files:
            file_context, _file_refs = process_jlens_files(files)
        
        # Use JLens-specific system message
        system_message = get_jlens_system_message(user_name, file_context)
    else:
        # Use combined pre-prompt system for other workspaces
        if message.pre_prompt:
            system_message = combine_prompts(message.pre_prompt, user_name)
        else:
            system_message = get_model_specific_system_message(message.model_type or "gpt-4.1-mini", user_name)
    

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_message},
        *[
            {"role": msg.role, "content": msg.content}
            for msg in messages_db
            if msg.role != "tool"
        ],
    ]

    mcp_configs = get_mcp_by_workspace_id(db, user_msg.workspace_id)
    client = ChatClient(model_name=message.model_type)
    await client.load_mcp_tools(mcp_configs)
    client.messages = messages

    async def token_stream():
        try: 
            collected_response = ""
            token_count = 0
            
            # Enhanced parameters for JLens workspace
            temperature = 0.7 if workspace and workspace.name == "JLens" else 0
            
            async for token in client.generate_response(temperature=temperature):
                token_count += 1
                
                if token != "[DONE]":
                    # Ensure token is string to prevent sequence errors
                    token = str(token) if not isinstance(token, str) else token
                    collected_response += token
                    to_yield = json.dumps({"token": token})
                    yield f"data: {to_yield}\n\n"
            
            
            # Append model icon and name to the response
            model_signature = f"\n\n[MODEL:{message.model_type}]"
            
            # Enhance response quality for JLens workspace
            if workspace and workspace.name == "JLens":
                collected_response = enhance_response_quality(collected_response)
            
            collected_response += model_signature
            
            # Send the model signature as final tokens
            for char in model_signature:
                to_yield = json.dumps({"token": char})
                yield f"data: {to_yield}\n\n"
                
            # Send final done signal
            yield f"data: {json.dumps({'token': '[DONE]'})}\n\n"
            
            # Estimate tokens for analytics
            input_text = " ".join([m.get("content", "") for m in messages])
            input_tokens = estimate_tokens(input_text)
            output_tokens = estimate_tokens(collected_response)
                
            # Save message with token tracking
            assistant_msg = create_message(
                db=db,
                user_id=user_id,
                msg_data=MessageCreate(
                    conversation_id=user_msg.conversation_id,
                    workspace_id=message.workspace_id,
                    content=collected_response,
                    role="assistant",
                    model_type=message.model_type,
                    chat_type=message.chat_type,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
            )
            conversation = db.query(Conversation).filter_by(id=user_msg.conversation_id).first()
            msg_count = db.query(Message).filter_by(conversation_id=user_msg.conversation_id).count()
            if msg_count == 2 and conversation and conversation.title == "New Conversation":
                first_user_msg = db.query(Message).filter_by(
                    conversation_id=user_msg.conversation_id, 
                    role="user"
                ).first()
                if first_user_msg:
                    new_title = generate_title(
                        {"role": "user", "content": first_user_msg.content},
                        message.model_type,
                        collected_response
                    )
                    if new_title != "New Conversation":
                        conversation.title = new_title
                        db.commit()
                                   
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            raise HTTPException(status_code=500, detail=f"Failed to stream model response: {str(e)}")

    return StreamingResponse(
        token_stream(), 
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )

def get_last_user_message(db: Session, conversation_id: UUID):
    last_user_msg = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .first()
    )

    if not last_user_msg:
        raise HTTPException(status_code=404, detail="User message not found in conversation")

    return last_user_msg

def store_answer(
        db: Session,
        uid: UUID,
        messages: MessageCreate
):
    
    message = Message(
        conversation_id=messages.conversation_id,
        user_id=uid,
        workspace_id=messages.workspace_id,
        content=messages.content,
        role=messages.role,
        model_type=getattr(messages, "model_type", None),
        chat_type=getattr(messages, "chat_type", None),
        input_tokens=messages.input_tokens,
        output_tokens=messages.output_tokens,
    )

    db.add(message)
    db.commit()
    db.refresh(message)
    return message
