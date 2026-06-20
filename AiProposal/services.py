import io
import re
import time
import uuid
from fastapi.responses import StreamingResponse
import requests
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from db.models import ProposalQuestions, Message, ProposalMetadata, Conversation, Workspace, User
from .workspace_integration import (
    get_ai_proposal_workspace, 
    create_ai_proposal_conversation,
    ensure_ai_proposal_workspace_exists,
    is_ai_proposal_conversation
)
from .schemas import ProposalMetadataSchema, ScoredProposals, EditAnswersRequest
from .utils.input_parser import *
from sqlalchemy import asc, text
from .utils.get_n_matching_proposals import *
from .utils.prompts import *
import os
import asyncio
from fastapi import FastAPI, HTTPException, UploadFile
from openai import AzureOpenAI
import httpx
from azure.storage.blob import BlobServiceClient
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.document import Document as _Document
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from markdown2 import markdown
from bs4 import BeautifulSoup
import json
from .utils.prompts import AI_PROPOSAL_SYSTEM_PROMPT, DOCS_PROMPT
from fastapi import status
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta  # <-- CORRECT: Single import
from .Langgraph.main import generate_proposal_langgraph


#Azure Search configuration
AZURE_SEARCH_QUERY_TYPE = os.getenv("AZURE_SEARCH_QUERY_TYPE", "simple")
AZURE_SEARCH_USE_SEMANTIC_SEARCH = os.getenv("AZURE_SEARCH_USE_SEMANTIC_SEARCH", "false")
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
AZURE_SEARCH_SERVICE_INDEXER_GENERATED_PROPOSALS_NAME = os.getenv("AZURE_SEARCH_SERVICE_INDEXER_GENERATED_PROPOSALS_NAME", "generated-proposals-indexer")

AZURE_SEARCH_AI_PROPOSAL_WORKSPACE_INDEXER = os.getenv("AZURE_SEARCH_AI_PROPOSAL_WORKSPACE_INDEXER", "ai-proposal-workspace-indexer")
AI_PROPOSAL_WORKSPACE_CONTAINER_NAME = os.getenv("AI_PROPOSAL_WORKSPACE_CONTAINER_NAME", "workspaces")  # Fallback to main container
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL_NAME_1")
AZURE_OPENAI_PREVIEW_API_VERSION = os.getenv("AZURE_OPENAI_PREVIEW_API_VERSION", "2024-05-01-preview")
PROPOSAL_TEMPLATE_CONTAINER_NAME = os.getenv("PROPOSAL_TEMPLATE_CONTAINER_NAME", "workspaces")  # Fallback
GENERATED_PROPOSALS_CONTAINER_NAME = os.getenv("GENERATED_PROPOSALS_CONTAINER_NAME", "workspaces")  # Fallback
AI_PROPOSAL_SALES_QAS_CONTAINER_NAME = os.getenv("AI_PROPOSAL_SALES_QAS_CONTAINER_NAME", "ai-proposal-sales-qas")

# 

blob_service_client = BlobServiceClient.from_connection_string(
    os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
)


headers = {
    "api-key": AZURE_OPENAI_KEY,
    "Content-Type": "application/json",
}

# Azure OpenAI client (same as workspace)
httpx_client = httpx.Client(
    base_url=AZURE_OPENAI_ENDPOINT,
    headers={"api-key": AZURE_OPENAI_KEY},
    timeout=60.0,
)

azure_client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version="2024-05-01-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    http_client=httpx_client,
)

async def update_message_service(request, db):
    message = db.query(Message).filter(
        Message.conversation_id == request.conversation_id,
        Message.id == request.msg_id
    ).first()
    if not message:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Message not found")
    message.content = request.content
    db.commit()
    return {"message": f"Message {request.msg_id} updated successfully"}

async def fetch_chat_completion(prompt: str, system_prompt: str, docs_prompt: str, conversation_id: str, data_source=None) -> dict:
    """Send a chat completion request using Azure OpenAI client (same as workspace)"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    try:
        response = azure_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            temperature=float(AZURE_OPENAI_TEMPERATURE),
            max_tokens=10000,
            top_p=float(AZURE_OPENAI_TOP_P),
        )
        
        # Convert to dict format expected by the rest of the code
        return {
            "choices": [{
                "message": {
                    "content": response.choices[0].message.content
                }
            }]
        }
        
    except Exception as e:
        print(f"Azure OpenAI error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

def iter_block_items(parent):
    """
    Yield each paragraph and table from a docx Document or a table cell, in document order.
    """
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("Unsupported parent type.")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def get_all_text_from_doc(doc):
    """
    Extracts text from paragraphs and tables in order.
    For tables, joins cell text with tabs.
    """
    parts = []
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            if block.text.strip():
                parts.append(block.text.strip())
        elif isinstance(block, Table):
            for row in block.rows:
                row_text = [cell.text.strip() for cell in row.cells]
                if any(row_text):  # only add if there's content
                    parts.append("\t".join(row_text))
    return "\n".join(parts)


def get_proposal_content(proposals: list[ScoredProposals]) -> list[str]:
    """Get proposal content from blob storage with error handling"""
    combined_content = []

    for p in proposals:
        try:
            # Use fallback container if template container doesn't exist
            container_name = PROPOSAL_TEMPLATE_CONTAINER_NAME or "workspaces"
            
            blob_client = blob_service_client.get_blob_client(
                container=container_name,
                blob='templates/' + p.proposal.name
            )
            blob_bytes = blob_client.download_blob().readall()
            
            # Load the Word document from bytes
            doc = Document(io.BytesIO(blob_bytes))

            # Extract all text
            text = get_all_text_from_doc(doc)
            combined_content.append(text)
            
        except Exception as e:
            print(f"Warning: Could not load proposal template {p.proposal.name}: {e}")
            # Add placeholder content instead of failing
            combined_content.append(f"Template content for {p.proposal.name} not available")
    
    return combined_content


async def read_sales_call_questions_docx():
    """
    Reads the 'sales_call_questions.docx' file from the PROPOSAL_TEMPLATE_CONTAINER_NAME container in Azure Blob Storage
    and returns it as a downloadable HTTP response.
    """
    blob_name = "templates/sales_call_questions.docx"
    blob_client = blob_service_client.get_blob_client(
        container=PROPOSAL_TEMPLATE_CONTAINER_NAME,
        blob=blob_name
    )
    blob_bytes = blob_client.download_blob().readall()
    doc_stream = io.BytesIO(blob_bytes)
    doc_stream.seek(0)
    return StreamingResponse(
        doc_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": "attachment; filename=sales_call_questions.docx"
        }
    )

async def upload_sales_call_questions_docx(user_id: UUID, conversation_id: UUID, file: UploadFile):
    try:
        blob_service_client = AsyncBlobServiceClient.from_connection_string(
            os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        )
        container_client = blob_service_client.get_container_client(AI_PROPOSAL_SALES_QAS_CONTAINER_NAME)
        blob_name = f"{user_id}----{conversation_id}.docx"

        # Upload the file asynchronously to the container
        await container_client.upload_blob(blob_name, await file.read(), overwrite=True)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"message": blob_name}
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": f"File upload failed: {str(e)}"}
        )
    
async def read_uploaded_sales_call_questions_docx(user_id: UUID, conversation_id: UUID):
    """Reads the uploaded sales call questions DOCX file for a specific user and conversation from Azure Blob Storage.
    If the file is not present, returns an empty string.
    """
    blob_name = f"{user_id}----{conversation_id}.docx"
    try:
        blob_service_client = AsyncBlobServiceClient.from_connection_string(
            os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        )
        blob_client = blob_service_client.get_blob_client(
            container=AI_PROPOSAL_SALES_QAS_CONTAINER_NAME,
            blob=blob_name
        )
        blob_bytes = await (await blob_client.download_blob()).readall()
        doc_stream = io.BytesIO(blob_bytes)
        doc_stream.seek(0)

        # Load the Word document from bytes
        doc = Document(io.BytesIO(blob_bytes))

        # Extract all text
        text = get_all_text_from_doc(doc)
        return text
    except Exception:
        # File not found or any error: return empty string
        return ""
























async def generate_proposal(conversation_id: UUID, db: Session, uid: UUID, user_prompt: str = None):
    """
    Generate a proposal based on user prompt and sales call questionnaire
    """
    # 1. Get current user
    current_user = db.query(User).filter_by(id=uid).first()
    if not current_user:
        raise ValueError(f"User {uid} not found")

    print("=" * 100)
    print("Entered generate_proposal")
    print(f"Conversation ID: {conversation_id}")
    print(f"User ID: {uid}")
    print("=" * 100)
    
    # 2. RETRIEVE USER PROMPT FROM DATABASE (if not provided)
    
    
    # 3. RETRIEVE SALES CALL QUESTIONNAIRE FROM BLOB STORAGE
    client_context_qas = await read_uploaded_sales_call_questions_docx(uid, conversation_id)
    
    # 4. Call generate_proposal_langgraph() with both inputs
    ggg_output = generate_proposal_langgraph(
        questionnaire=client_context_qas, 
        user_prompt=user_prompt
    )
    
    print("Received output from generate_proposal_langgraph:")
    print(ggg_output)
    
    # 5. GET DATA FROM ggg_output
    proposal_text = ggg_output.get("proposal_text", "")
    sections = ggg_output.get("sections", [])
    
    # ✅ Get citations as a list
    citations_data = ggg_output.get("citations", {})
    if isinstance(citations_data, dict) and "citations" in citations_data:
        citations_list = citations_data["citations"]
    elif isinstance(citations_data, list):
        citations_list = citations_data
    else:
        citations_list = []
    
    # Ensure citations is a list
    if not isinstance(citations_list, list):
        citations_list = []
    
    # 6. Store generated proposal to DB
    first_message = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        .scalars()
        .first()
    )
    
    if not first_message:
        raise ValueError(f"No messages found for conversation {conversation_id}")
    
    # Precompute created_at timestamps
    now = datetime.now(timezone.utc)
    delta = timedelta(milliseconds=1)
    created_at_assistant = now
    created_at_tool = now + delta
    
    # Store assistant message with complete proposal
    new_message = Message(
        user_id=first_message.user_id,
        conversation_id=conversation_id,
        workspace_id=first_message.workspace_id,
        content=proposal_text,
        role="assistant",
        model_type="",
        chat_type="hybrid",
        input_tokens=0,
        output_tokens=0,
        created_at=created_at_assistant
    )
    
    # Store citations as tool message
    citations_for_db = {"citations": citations_list}
    reference_proposals = Message(
        user_id=first_message.user_id,
        conversation_id=conversation_id,
        workspace_id=first_message.workspace_id,
        content=json.dumps(citations_for_db),
        role="tool",
        model_type="",
        chat_type="hybrid",
        input_tokens=0,
        output_tokens=0,
        created_at=created_at_tool
    )
    
    db.add(new_message)
    db.add(reference_proposals)
    db.commit()
    
    # 7. Upload proposal to blob storage
    try:
        proposal_docx_upload(proposal_text, current_user.email, conversation_id)
        print(f"Successfully uploaded proposal to blob storage")
    except Exception as e:
        print(f"Warning: Could not upload to blob storage: {e}")
    
    print("*" * 100)
    print("Proposal generation and storage completed successfully.")
    print("*" * 100)
    
    # 8. FORMAT SECTIONS FOR FRONTEND
    formatted_sections = []
    
    if sections and len(sections) > 0:
        for section in sections:
            if isinstance(section, dict):
                formatted_sections.append({
                    "prompt": section.get("prompt", "Section"),
                    "response": section.get("response", ""),
                    "error": section.get("error")
                })
            else:
                formatted_sections.append({
                    "prompt": "Section",
                    "response": str(section),
                    "error": None
                })
    elif proposal_text:
        formatted_sections = parse_sections_from_text(proposal_text)
    else:
        formatted_sections = [{
            "prompt": "Proposal",
            "response": "No content generated",
            "error": None
        }]
    
    # 9. ✅ RETURN RESPONSE - citations as dict matching CitationsSchema
    return {
        "msg_id": new_message.id,
        "proposal": formatted_sections,
        "citations": {
            "citations": [
                {
                    "filepath": c.get("filepath", ""),
                    "url": c.get("url", "")
                }
                for c in citations_list if isinstance(c, dict)
            ]
        }
    }
























def edit_answers(request: EditAnswersRequest, db: Session):
    try:
        conv_messages = (
            db.query(Message)
            .filter(Message.conversation_id == request.conversation_id)
            .order_by(asc(Message.created_at))
            .all()
        )

        for item in request.to_edit:
            qid_index = int(item.qid) * 2 -1
            if qid_index < len(conv_messages):
                conv_messages[qid_index].content = item.content
            else:
                raise IndexError(f"Invalid qid: {item.qid}, out of range for conversation messages.")

        db.commit()
        return {"message": "success"}
    except Exception as e:
        db.rollback()
        return {"message": str(e)}


async def follow_up_proposal_service(conversation_id: UUID, recent_message: str, new_message: str, db: Session, current_user: User):
    
    # workspace_name = (
    #     db.query(Workspace.name)
    #     .join(Conversation, Workspace.id == Conversation.workspace_id)
    #     .filter(Conversation.id == conversation_id)
    #     .scalar()
    # )
    system_prompt="""Update the entire proposal that is provided based on the new instruction provided.
Give the full updated proposal. Don't add anything other than updated proposal in the response
STRICTLY generate the proposal content in a WELL-STRUCTURED MARKDOWN FORMAT, use h1 heading style for section headings, h2, h3 for appropriate sub-headings, ul for bullet points and ol for numbered lists.
"""
    prompt = (
        f"Proposal:\n{recent_message}\n"
        f"New instruction:\n{new_message}"
    )
    docs_prompt = """
Use the documents as a reference to generate the updated proposal.
Adhere to the user and system instructions as well.
"""
    try:
        llm_response = await fetch_chat_completion(
            prompt, system_prompt, docs_prompt, str(conversation_id)
        )

        print("LLM response received in follow-up service:")
        print(llm_response) 

        assistant_content = llm_response["choices"][0]["message"]["content"]
        # tool_content = llm_response["choices"][0]["messages"][0]["content"]
        tool_content = json.dumps({
            "citations": []
        })
        last_message = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at.desc()).first()
        if not last_message:
            return {"message": "No message found to update"}
        
        # Precompute created_at timestamps
        now = datetime.now(timezone.utc)
        delta = timedelta(milliseconds=1)
        created_at_user = now
        created_at_assistant = now + delta
        created_at_tool = now + delta + delta

        # Save user message
        user_msg = Message(
            user_id=last_message.user_id,
            conversation_id=conversation_id,
            workspace_id=last_message.workspace_id,
            content=new_message,
            role="user",
            model_type="",
            chat_type="hybrid",
            input_tokens=0,
            output_tokens=0,
            created_at=created_at_user
        )
        # Save assistant message
        assistant_msg = Message(
            user_id=last_message.user_id,
            conversation_id=conversation_id,
            workspace_id=last_message.workspace_id,
            content=assistant_content,
            role="assistant",
            model_type="",
            chat_type="hybrid",
            input_tokens=0,
            output_tokens=0,
            created_at=created_at_assistant
        )
        # Save tool message
        tool_msg = Message(
            user_id=last_message.user_id,
            conversation_id=conversation_id,
            workspace_id=last_message.workspace_id,
            content=tool_content,
            role="tool",
            model_type="",
            chat_type="hybrid",
            input_tokens=0,
            output_tokens=0,
            created_at=created_at_tool
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.add(tool_msg)
        db.commit()
        
        return {
                "msg_id": assistant_msg.id,
                "assistant": assistant_content, 
                "tool": tool_content,
                "replace_existing": True,
                "target_message_id": str(user_msg.id)
            }
    except Exception as e:
        db.rollback()
        return {"message": str(e)}
        

def add_content_to_doc(doc, content):
    """
    Convert Markdown or HTML content to properly formatted DOCX content.
    Automatically detects whether the input is Markdown or HTML.
    """
    # Detect if the input is Markdown (no HTML tags) or HTML
    if "<" not in content and ">" not in content:
        # Convert Markdown to HTML
        html_content = markdown(content, extras=["fenced-code-blocks"])
    else:
        # Assume it's already HTML
        html_content = content

    # Parse the HTML using BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    for element in soup:
        if element.name == "h1":
            doc.add_paragraph(element.get_text(), style="Heading 1")
        elif element.name == "h2":
            doc.add_paragraph(element.get_text(), style="Heading 2")
        elif element.name == "h3":
            doc.add_paragraph(element.get_text(), style="Heading 3")
        elif element.name == "ul":
            for li in element.find_all("li"):
                p = doc.add_paragraph()  # No specific style applied
                p.add_run("• ").bold = False  # Add bullet point manually
                p.add_run(li.get_text())
        elif element.name == "ol":
            counter = 1
            for li in element.find_all("li"):
                p = doc.add_paragraph()  # No specific style applied
                p.add_run(f"{counter}. ").bold = False  # Add numbered point manually
                p.add_run(li.get_text())
                counter += 1
        elif element.name == "p":
            doc.add_paragraph(element.get_text())
        elif element.name == "strong":
            p = doc.add_paragraph()
            p.add_run(element.get_text()).bold = True
        elif element.name == "em":
            p = doc.add_paragraph()
            p.add_run(element.get_text()).italic = True
        elif element.name == "code":
            # For inline code or code blocks
            p = doc.add_paragraph(style="Quote")  # You can choose another style like "Code"
            p.add_run(element.get_text()).font.name = "Courier New"  # Use monospace font for code
        elif element.name == "br":
            # Handle line breaks
            doc.add_paragraph("")
    
    # Ensure proper formatting (e.g., spacing between paragraphs)
    for paragraph in doc.paragraphs:
        paragraph.paragraph_format.space_after = Pt(6)
        paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT












def proposal_docx(conversation_id: UUID, db: Session):
    try:
        import os
        import re
        import json
        import io
        from datetime import datetime
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor, Cm, Emu
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
        from docx.enum.section import WD_SECTION
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        from typing import Optional, Dict, Any
        from uuid import UUID
        from sqlalchemy import asc

        # =====================================================
        # JMAN brand colours
        # =====================================================
        _NAVY    = RGBColor(0x17, 0x38, 0x45)
        _PINK    = RGBColor(0xFF, 0x61, 0x96)
        _DARK    = RGBColor(0x1D, 0x1C, 0x1C)
        _GRAY    = RGBColor(0x80, 0x80, 0x80)
        _DEEP    = RGBColor(0x19, 0x10, 0x5B)
        _WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
        _BORDER  = RGBColor(0xDD, 0xDD, 0xDD)
        _RED     = RGBColor(0xCC, 0x00, 0x00)
        _AMBER   = RGBColor(0xCC, 0x77, 0x00)
        _GREEN   = RGBColor(0x2E, 0x7D, 0x32)
        _FONT = "Arial"
        _ZEBRA = "F9F9F9"

        # =====================================================
        # Page geometry (A4)
        # =====================================================
        _PAGE_W_CM = 21.0
        _PAGE_H_CM = 29.7

        # =====================================================
        # Brand asset locations
        # =====================================================
        _ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),  "assets", "jman")
        _ASSET_FILES = {
            "logo_white":  "jman_logo_white.png",
            "logo_navy":   "jman_logo_navy.png",
            "corner_mark": "jman_corner_mark.png",
            "cover_bg":    "cover_background.jpg",
        }

        def _asset(name: str) -> Optional[str]:
            path = os.path.join(_ASSETS_DIR, _ASSET_FILES[name])
            return path if os.path.isfile(path) else None

        # =====================================================
        # Low-level helpers
        # =====================================================
        def _run(para, text, size_pt, bold=False, italic=False, color=None, font=_FONT):
            run = para.add_run(text)
            run.font.name = font
            run.font.size = Pt(size_pt)
            run.font.bold = bold
            run.font.italic = italic
            if color:
                run.font.color.rgb = color
            return run

        def _set_cell_shading(cell, fill_hex: str):
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:shd")):
                tcPr.remove(old)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), fill_hex)
            tcPr.append(shd)

        def _set_cell_borders(cell, color_hex="DDDDDD", sz=4):
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:tcBorders")):
                tcPr.remove(old)
            tcBorders = OxmlElement("w:tcBorders")
            for side in ("top", "left", "bottom", "right"):
                el = OxmlElement(f"w:{side}")
                el.set(qn("w:val"), "single")
                el.set(qn("w:sz"), str(sz))
                el.set(qn("w:space"), "0")
                el.set(qn("w:color"), color_hex)
                tcBorders.append(el)
            tcPr.append(tcBorders)

        def _set_cell_margins(cell, top=80, bottom=80, left=110, right=110):
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            mar = OxmlElement("w:tcMar")
            for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
                el = OxmlElement(f"w:{side}")
                el.set(qn("w:w"), str(val))
                el.set(qn("w:type"), "dxa")
                mar.append(el)
            tcPr.append(mar)

        def _set_table_width(tbl, width_twips: int):
            tbl_el = tbl._tbl
            tblPr = tbl_el.find(qn("w:tblPr"))
            if tblPr is None:
                tblPr = OxmlElement("w:tblPr")
                tbl_el.insert(0, tblPr)
            for old in tblPr.findall(qn("w:tblW")):
                tblPr.remove(old)
            tblW = OxmlElement("w:tblW")
            tblW.set(qn("w:w"), str(width_twips))
            tblW.set(qn("w:type"), "dxa")
            tblStyle = tblPr.find(qn("w:tblStyle"))
            if tblStyle is not None:
                tblStyle.addnext(tblW)
            else:
                tblPr.insert(0, tblW)

        def _pink_divider(doc):
            """Add a pink divider line."""
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "8")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "FF6196")  # Pink color
            pBdr.append(bottom)
            pPr.append(pBdr)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(10)
            return p

        def _spacer(doc, pt=8):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(pt)
            return p

        def _add_floating_picture(paragraph, image_path, width, height, behind_doc=True, name="Picture"):
            run = paragraph.add_run()
            run.add_picture(image_path, width=width, height=height)
            drawing = run._r.find(qn("w:drawing"))
            inline = drawing.find(qn("wp:inline"))

            extent = inline.find(qn("wp:extent"))
            docPr = inline.find(qn("wp:docPr"))
            graphic = inline.find(qn("a:graphic"))
            inline.remove(extent)
            inline.remove(docPr)
            inline.remove(graphic)
            docPr.set("name", name)

            anchor = OxmlElement("wp:anchor")
            anchor.set("distT", "0")
            anchor.set("distB", "0")
            anchor.set("distL", "0")
            anchor.set("distR", "0")
            anchor.set("simplePos", "0")
            anchor.set("relativeHeight", "251658240")
            anchor.set("behindDoc", "1" if behind_doc else "0")
            anchor.set("locked", "0")
            anchor.set("layoutInCell", "1")
            anchor.set("allowOverlap", "1")

            simplePos = OxmlElement("wp:simplePos")
            simplePos.set("x", "0")
            simplePos.set("y", "0")

            posH = OxmlElement("wp:positionH")
            posH.set("relativeFrom", "page")
            offH = OxmlElement("wp:posOffset")
            offH.text = "0"
            posH.append(offH)

            posV = OxmlElement("wp:positionV")
            posV.set("relativeFrom", "page")
            offV = OxmlElement("wp:posOffset")
            offV.text = "0"
            posV.append(offV)

            effectExtent = OxmlElement("wp:effectExtent")
            for side in ("l", "t", "r", "b"):
                effectExtent.set(side, "0")

            wrapNone = OxmlElement("wp:wrapNone")

            anchor.append(simplePos)
            anchor.append(posH)
            anchor.append(posV)
            anchor.append(extent)
            anchor.append(effectExtent)
            anchor.append(wrapNone)
            anchor.append(docPr)
            anchor.append(graphic)

            drawing.remove(inline)
            drawing.append(anchor)
            return run

        def _add_page_number_field(paragraph, size_pt=8, color=_GRAY):
            """Insert a PAGE field into the given paragraph (new run)."""
            run = paragraph.add_run()
            run.font.size = Pt(size_pt)
            run.font.color.rgb = color
            fld = OxmlElement('w:fld')
            instr = OxmlElement('w:instrText')
            instr.text = 'PAGE'
            fld.append(instr)
            run._r.append(fld)

        # =====================================================
        # Styled content parsing and application
        # =====================================================
        _BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
        _SECTION_DIVIDER_RE = re.compile(r"^---\s*$|^___\s*$|^\*\*\*\s*$")  # Matches ---, ___, ***

        def _add_inline_runs(p, text, size_pt, color, bold=False, italic=False):
            pos = 0
            for m in _BOLD_RE.finditer(text):
                if m.start() > pos:
                    _run(p, text[pos:m.start()], size_pt, bold=bold, italic=italic, color=color)
                _run(p, m.group(1), size_pt, bold=True, italic=italic, color=color)
                pos = m.end()
            if pos < len(text):
                _run(p, text[pos:], size_pt, bold=bold, italic=italic, color=color)

        def _status_color(value: str):
            v = value.strip().lower()
            if any(k in v for k in ("blocked", "at risk", "failed", "delayed")):
                return _RED
            if any(k in v for k in ("in progress", "pending", "ongoing", "review")):
                return _AMBER
            if any(k in v for k in ("resolved", "done", "complete", "approved", "on track")):
                return _GREEN
            return _DARK

        def _render_table(doc, header_cells, body_rows):
            n_cols = len(header_cells)
            tbl = doc.add_table(rows=1, cols=n_cols)
            tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
            tbl.style = "Table Grid"

            content_width_twips = int((_PAGE_W_CM - 3.5) * 567)
            if n_cols == 2:
                widths = [int(content_width_twips * 0.7), int(content_width_twips * 0.3)]
            else:
                widths = [content_width_twips // n_cols] * n_cols
            _set_table_width(tbl, sum(widths))

            hdr_row = tbl.rows[0]
            for i, text in enumerate(header_cells):
                cell = hdr_row.cells[i]
                cell.width = Pt(widths[i] / 20)
                _set_cell_shading(cell, "173845")
                _set_cell_borders(cell, "DDDDDD", 4)
                _set_cell_margins(cell)
                cell.paragraphs[0].clear() if cell.paragraphs[0].runs else None
                p = cell.paragraphs[0]
                for r in list(p.runs):
                    r._r.getparent().remove(r._r)
                _run(p, text, 10, bold=True, color=_WHITE)

            for ridx, row_vals in enumerate(body_rows):
                row = tbl.add_row()
                fill = "FFFFFF" if ridx % 2 == 0 else _ZEBRA
                for i, val in enumerate(row_vals):
                    cell = row.cells[i]
                    cell.width = Pt(widths[i] / 20)
                    _set_cell_shading(cell, fill)
                    _set_cell_borders(cell, "DDDDDD", 4)
                    _set_cell_margins(cell)
                    p = cell.paragraphs[0]
                    is_status_col = (n_cols == 2 and i == 1)
                    color = _status_color(val) if is_status_col else _DARK
                    _run(p, val, 10, bold=is_status_col, color=color)
            return tbl

        def _apply_styled_content(doc, raw_text: str, heading_counter: list):
            """Apply styled content with pink dividers between major sections."""
            lines = raw_text.splitlines()
            i = 0
            n = len(lines)
            section_count = 0
            
            while i < n:
                line = lines[i]
                stripped = line.strip()

                if not stripped:
                    doc.add_paragraph().paragraph_format.space_after = Pt(4)
                    i += 1
                    continue

                # Check for section divider markers (---, ___, ***)
                if _SECTION_DIVIDER_RE.match(stripped):
                    _pink_divider(doc)
                    section_count += 1
                    i += 1
                    continue

                # Check for table
                if stripped.startswith("|") and i + 1 < n and re.match(r"^\|?[\s:|-]+\|?$", lines[i + 1].strip()):
                    header_cells = [c.strip() for c in stripped.strip("|").split("|")]
                    j = i + 2
                    body_rows = []
                    while j < n and lines[j].strip().startswith("|"):
                        body_rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                        j += 1
                    _render_table(doc, header_cells, body_rows)
                    _spacer(doc, pt=8)
                    i = j
                    continue

                # Check for heading level 1
                if stripped.startswith("# "):
                    # Add pink divider before major headings (except the first one)
                    if heading_counter[0] > 0:
                        _pink_divider(doc)
                    
                    heading_counter[0] += 1
                    text = stripped[2:].strip()
                    p = doc.add_paragraph()
                    pf = p.paragraph_format
                    pf.left_indent = Cm(1.02)
                    pf.first_line_indent = Cm(-1.02)
                    pf.space_before = Pt(14)
                    pf.space_after = Pt(8)
                    try:
                        pf.tab_stops.add_tab_stop(Cm(1.02))
                    except Exception:
                        pass
                    _run(p, f"{heading_counter[0]}\t", 12, bold=True, color=_DEEP)
                    _add_inline_runs(p, text, 12, _DEEP, bold=True)
                    i += 1
                    continue

                # Check for heading level 2
                if stripped.startswith("## "):
                    text = stripped[3:].strip()
                    p = doc.add_paragraph()
                    p.paragraph_format.space_before = Pt(10)
                    p.paragraph_format.space_after = Pt(4)
                    _add_inline_runs(p, text, 11, _PINK, bold=True)
                    i += 1
                    continue

                # Check for bullet points
                if stripped.startswith("- ") or stripped.startswith("* "):
                    text = stripped[2:].strip()
                    p = doc.add_paragraph()
                    pf = p.paragraph_format
                    pf.left_indent = Cm(1.27)
                    pf.first_line_indent = Cm(-0.64)
                    pf.space_after = Pt(4)
                    pf.line_spacing = 1.15
                    try:
                        pf.tab_stops.add_tab_stop(Cm(1.27))
                    except Exception:
                        pass
                    _run(p, "•\t", 10, color=_PINK)
                    _add_inline_runs(p, text, 10, _DARK)
                    i += 1
                    continue

                # Regular paragraph
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(8)
                p.paragraph_format.line_spacing = 1.15
                _add_inline_runs(p, stripped, 10, _DARK)
                i += 1

        # =====================================================
        # Cover page
        # =====================================================
        def _build_cover_section(doc, client_name: str):
            sec = doc.sections[0]
            sec.page_width = Cm(_PAGE_W_CM)
            sec.page_height = Cm(_PAGE_H_CM)
            sec.top_margin = Cm(1.0)
            sec.bottom_margin = Cm(1.0)
            sec.left_margin = Cm(1.75)
            sec.right_margin = Cm(1.75)

            bg = _asset("cover_bg")
            if bg:
                p_bg = doc.add_paragraph()
                p_bg.paragraph_format.space_after = Pt(0)
                _add_floating_picture(
                    p_bg, bg, Cm(_PAGE_W_CM), Cm(_PAGE_H_CM), behind_doc=True, name="Cover Background"
                )

            logo = _asset("logo_white")
            if logo:
                p_logo = doc.add_paragraph()
                p_logo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                p_logo.paragraph_format.space_after = Pt(0)
                r = p_logo.add_run()
                r.add_picture(logo, width=Cm(8.0))

            p_spacer = doc.add_paragraph()
            p_spacer.paragraph_format.space_after = Pt(210)

            p_rule = doc.add_paragraph()
            pPr = p_rule._p.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "4")
            bottom.set(qn("w:space"), "4")
            bottom.set(qn("w:color"), "FFFFFF")
            pBdr.append(bottom)
            pPr.append(pBdr)
            p_rule.paragraph_format.space_after = Pt(12)

            p_caption = doc.add_paragraph()
            p_caption.paragraph_format.space_after = Pt(14)
            _run(p_caption, "STATEMENT OF WORK BETWEEN", 15, bold=True, color=_PINK)

            p_company = doc.add_paragraph()
            p_company.paragraph_format.space_after = Pt(6)
            _run(p_company, client_name, 30, bold=True, color=_NAVY)

            p_and = doc.add_paragraph()
            p_and.paragraph_format.space_after = Pt(6)
            _run(p_and, "And", 16, italic=True, color=_GRAY)

            p_jman = doc.add_paragraph()
            p_jman.paragraph_format.space_after = Pt(0)
            _run(p_jman, "JMAN Group", 30, bold=True, color=_NAVY)

        # =====================================================
        # Content section: header (logo), footer (client, version, date, page, mark)
        # =====================================================
        def _build_content_section(doc, client_name="Client", version="v1.0"):
            sec = doc.add_section(WD_SECTION.NEW_PAGE)
            sec.page_width = Cm(_PAGE_W_CM)
            sec.page_height = Cm(_PAGE_H_CM)
            sec.top_margin = Cm(1.8)
            sec.bottom_margin = Cm(0.9)
            sec.left_margin = Cm(1.75)
            sec.right_margin = Cm(1.75)
            sec.header_distance = Cm(1.0)
            sec.footer_distance = Cm(0.9)
            sec.header.is_linked_to_previous = False
            sec.footer.is_linked_to_previous = False

            # Header
            header = sec.header
            for p in list(header.paragraphs):
                p.clear()
            p_logo = header.paragraphs[0]
            p_logo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p_logo.paragraph_format.space_after = Pt(0)
            logo = _asset("logo_navy")
            if logo:
                r = p_logo.add_run()
                r.add_picture(logo, width=Cm(3.2))

            # Footer
            footer = sec.footer
            for p in list(footer.paragraphs):
                p.clear()

            fp = footer.paragraphs[0]
            fp.paragraph_format.space_before = Pt(4)
            fp.paragraph_format.space_after = Pt(0)

            # Navy top border
            pPr = fp._p.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            top_bdr = OxmlElement("w:top")
            top_bdr.set(qn("w:val"), "single")
            top_bdr.set(qn("w:sz"), "8")
            top_bdr.set(qn("w:space"), "4")
            top_bdr.set(qn("w:color"), "173845")
            pBdr.append(top_bdr)
            pPr.append(pBdr)

            # Tab stops
            fp.paragraph_format.tab_stops.clear_all()
            fp.paragraph_format.tab_stops.add_tab_stop(Cm(0), WD_TAB_ALIGNMENT.LEFT)
            fp.paragraph_format.tab_stops.add_tab_stop(Cm(8.5), WD_TAB_ALIGNMENT.CENTER)
            fp.paragraph_format.tab_stops.add_tab_stop(Cm(17.5), WD_TAB_ALIGNMENT.RIGHT)

            month_year = datetime.now().strftime("%B %Y")

            # Left: client
            _run(fp, f"Circulation Limited: {client_name}", 8, color=_GRAY)
            _run(fp, "\t", 8)

            # Centre: version
            _run(fp, f"Version {version}", 8, color=_GRAY)
            _run(fp, "\t", 8)

            # Right: month‑year, page number, corner mark
            _run(fp, month_year, 8, italic=True, color=_GRAY)
            _run(fp, " ", 8)

            # Page number field
            _add_page_number_field(fp, 8, _GRAY)

            _run(fp, " ", 8)

            # Corner mark
            mark = _asset("corner_mark")
            if mark:
                r = fp.add_run()
                r.add_picture(mark, height=Cm(0.45))

            return sec

        # =====================================================
        # Main logic
        # =====================================================
        
        # Count questions and get messages
        q_count = db.query(ProposalQuestions).count()
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(asc(Message.created_at))
            .all()
        )
        
        if len(messages) <= q_count * 2:
            raise HTTPException(status_code=404, detail="Not enough messages to generate proposal document.")
        
        # Find the last assistant message (proposal content)
        last_assistant_message = None
        for msg in reversed(messages):
            if msg.role == 'assistant':
                last_assistant_message = msg
                break
        
        if not last_assistant_message:
            raise HTTPException(status_code=404, detail="No assistant message found with proposal content.")
        
        last_proposal_content = last_assistant_message.content

        # Extract client name from questionnaire (first message)
        client_name = "Client"
        try:
            first_message = messages[0] if messages else None
            if first_message and first_message.content:
                q_data = json.loads(first_message.content)
                client_name = (
                    q_data.get("company_name") or
                    q_data.get("client_name") or
                    q_data.get("organization") or
                    q_data.get("company") or
                    "Client"
                )
        except Exception:
            pass

        # Create the document
        doc = Document()
        
        # 1. Cover page
        _build_cover_section(doc, client_name)
        
        # 2. Content section with header and footer
        version = "v1.0"
        _build_content_section(doc, client_name, version)
        
        # 3. Apply the proposal content with JMAN styling and pink dividers
        heading_counter = [0]
        _apply_styled_content(doc, last_proposal_content, heading_counter)

        # Save modified DOCX in memory
        doc_stream = io.BytesIO()
        doc.save(doc_stream)
        doc_stream.seek(0)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_name = "".join(c for c in client_name if c.isalnum() or c in " ._-").strip()
        clean_name = clean_name.replace(" ", "_")
        filename = f"Proposal_{clean_name}_{timestamp}.docx"

        # Return the DOCX file as a streaming response
        return StreamingResponse(
            doc_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Error generating proposal document: {str(e)}")



















def proposal_docx_upload(proposal_content: str, user_email: str, conversation_id: UUID):
    """Upload generated proposal to blob storage with error handling"""
    try:
        # Create a new document instead of using template if template doesn't exist
        doc = Document()
        
        # Add title
        title = doc.add_heading('AI Generated Proposal', 0)
        title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # Add content
        add_content_to_doc(doc, proposal_content)
        
        # Save modified DOCX in memory
        doc_stream = io.BytesIO()
        doc.save(doc_stream)
        doc_stream.seek(0)

        # Use main workspaces container as fallback
        container_name = GENERATED_PROPOSALS_CONTAINER_NAME or "workspaces"
        
        # Create blob client
        generated_blob_service_client = BlobServiceClient.from_connection_string(
            os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        )
        
        # Create blob path
        blob_path = f"ai-proposals/{user_email}/{conversation_id}/generated_proposal_{uuid.uuid4()}.docx"
        
        generated_blob_client = generated_blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_path
        )
        
        # Upload with error handling
        generated_blob_client.upload_blob(doc_stream, overwrite=True)
        print(f"Successfully uploaded proposal to {container_name}/{blob_path}")
        
    except Exception as e:
        print(f"Warning: Could not upload proposal to blob storage: {e}")
        # Don't raise exception, just log the warning

    
    # Trigger the indexer
    try:
        indexer_url = f'https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexers/{AZURE_SEARCH_SERVICE_INDEXER_GENERATED_PROPOSALS_NAME}/run?api-version=2020-06-30'
        headers = {
            'api-key': AZURE_SEARCH_KEY,
            'Content-Type': 'application/json'
        }
        response = requests.post(indexer_url, headers=headers)
        response.raise_for_status()
        

        # Poll for indexer status
        indexer_status_url = f'https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexers/{AZURE_SEARCH_SERVICE_INDEXER_GENERATED_PROPOSALS_NAME}/status?api-version=2020-06-30'

        max_retries = 10
        wait_time = 5
        last_run_status = "Unknown"
        last_run_error = ""

        for _ in range(max_retries):
            status_response = requests.get(indexer_status_url, headers=headers)
            status_data = status_response.json()

            last_run_status = status_data.get("lastResult", {}).get("status", "Unknown")
            last_run_error = status_data.get("lastResult", {}).get("errorMessage", "")

            if last_run_status in ["success", "transientFailure", "permanentFailure"]:
                break

            time.sleep(wait_time)
    except Exception as e:
        pass

async def upload_files(conversation_id: UUID, files: List[UploadFile], db: Session, user: User):
    uploaded_metadata = []

    for file in files:
        contents = await file.read()

        # Generate blob path
        blob_path = f"{user.email}----{conversation_id}/{user.email}----{conversation_id}----{file.filename}"

        # Upload to Azure
        await upload_file_to_azure_blob(contents, blob_path)  # <-- contents, not file

        uploaded_metadata.append({
            "filename": file.filename,
        })
    # Trigger the indexer
    try:
        indexer_url = f'https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexers/{AZURE_SEARCH_AI_PROPOSAL_WORKSPACE_INDEXER}/run?api-version=2020-06-30'
        headers = {
            'api-key': AZURE_SEARCH_KEY,
            'Content-Type': 'application/json'
        }
        response = requests.post(indexer_url, headers=headers)
        response.raise_for_status()
        

        # Poll for indexer status
        indexer_status_url = f'https://{AZURE_SEARCH_SERVICE}.search.windows.net/indexers/{AZURE_SEARCH_AI_PROPOSAL_WORKSPACE_INDEXER}/status?api-version=2020-06-30'

        max_retries = 10
        wait_time = 5
        last_run_status = "Unknown"
        last_run_error = ""

        for _ in range(max_retries):
            status_response = requests.get(indexer_status_url, headers=headers)
            status_data = status_response.json()

            last_run_status = status_data.get("lastResult", {}).get("status", "Unknown")
            last_run_error = status_data.get("lastResult", {}).get("errorMessage", "")

            if last_run_status in ["success", "transientFailure", "permanentFailure"]:
                break

            time.sleep(wait_time)
        
    except Exception as e:
        pass
    finally:
        return {
            "success": True, 
            "uploaded": uploaded_metadata,
            "indexer_status": last_run_status,
            "error_message": last_run_error,
            "status": last_run_status == "success"
        }

async def upload_file_to_azure_blob(file: bytes, blob_path: str):
    """Upload file to Azure Blob Storage with error handling"""
    try:
        blob_service_client = AsyncBlobServiceClient.from_connection_string(
            os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        )
        
        # Use fallback container if AI Proposal container is not configured
        container_name = AI_PROPOSAL_WORKSPACE_CONTAINER_NAME or "workspaces"
        
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(f"ai-proposals/{blob_path}")

        await blob_client.upload_blob(file, overwrite=True)
        print(f"Successfully uploaded file to {container_name}/ai-proposals/{blob_path}")
        
    except Exception as e:
        print(f"Warning: Could not upload file to blob storage: {e}")
        raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")

async def edit_proposal_llm_service(conversation_id: UUID, new_message: str, db: Session, current_user: User, message_id: UUID = None):

    if message_id:
        message = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.id == message_id
        ).first()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        proposal_msg = message.content
    
    system_prompt = f"""
User will provide a part of proposal's content along with new instructions to edit it.
You need to update ONLY the part of the proposal that is specified in the new instructions by taking context of whole proposal.

Whole proposal:
{proposal_msg}
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": new_message}
    ]

    try:
        response = azure_client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=messages,
            temperature=float(AZURE_OPENAI_TEMPERATURE),
            max_tokens=10000,
            top_p=float(AZURE_OPENAI_TOP_P),
        )
        
        return {
            "edited_proposal": response.choices[0].message.content
        }
        
    except Exception as e:
        print(f"Azure OpenAI error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")