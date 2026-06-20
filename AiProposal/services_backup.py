import io
import re
import time
import time
import uuid
from fastapi.responses import StreamingResponse
import requests
import requests
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from db.models import ProposalQuestions, Message, ProposalMetadata, Conversation, Workspace, User
from .schemas import ProposalMetadataSchema, ScoredProposals, EditAnswersRequest
from .utils.input_parser import *
from sqlalchemy import asc, text
from .utils.get_n_matching_proposals import *
from .utils.prompts import *
import os
import asyncio
from fastapi import FastAPI, HTTPException, UploadFile
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
import datetime
from datetime import datetime as dt


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

AZURE_SEARCH_AI_PROPOSAL_WORKSPACE_INDEXER = os.getenv("AZURE_SEARCH_AI_PROPOSAL_WORKSPACE_INDEXER")
AI_PROPOSAL_WORKSPACE_CONTAINER_NAME = os.getenv("AI_PROPOSAL_WORKSPACE_CONTAINER_NAME")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL_NAME_1")
AZURE_OPENAI_PREVIEW_API_VERSION = os.getenv("AZURE_OPENAI_PREVIEW_API_VERSION", "2024-05-01-preview")
PROPOSAL_TEMPLATE_CONTAINER_NAME = os.getenv("PROPOSAL_TEMPLATE_CONTAINER_NAME")
GENERATED_PROPOSALS_CONTAINER_NAME = os.getenv("GENERATED_PROPOSALS_CONTAINER_NAME", "generated-proposals")

# 

blob_service_client = BlobServiceClient.from_connection_string(
    os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
)


headers = {
    "api-key": AZURE_OPENAI_KEY,
    "Content-Type": "application/json",
}

# Base URL for chat completions
BASE_URL = f"{AZURE_OPENAI_ENDPOINT}openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/extensions/chat/completions?api-version={AZURE_OPENAI_PREVIEW_API_VERSION}"

async def fetch_chat_completion(prompt: str, system_prompt: str, docs_prompt: str, conversation_id: str, data_source=None) -> dict:
    """Send a chat completion request with Azure Cognitive Search as data source"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    data_sources = []
    workspace_data_source = {
        "type": "AzureCognitiveSearch",
        "parameters": {
            "endpoint": f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
            "key": AZURE_SEARCH_KEY,
            "indexName": "ai-proposal-workspace-index",
            "fieldsMapping": {
                "contentFields": ["content"],
                "titleField": "file_name",
                "urlField": "metadata_storage_path",
            },
            "inScope": False,
            "topNDocuments": 3,
            # "queryType": AZURE_SEARCH_QUERY_TYPE,
            # "semanticConfiguration": AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG,
            "roleInformation": docs_prompt,  # PROMPT TO INSTRUCT ABOUT USER UPLOADED DOCS
            "filter": f"conversation_id eq '{conversation_id}'",
            "strictness": int(AZURE_SEARCH_STRICTNESS),
        }
    }
    data_sources.append(workspace_data_source)
    # if (data_source):
    #     data_sources.append(data_source)

    body = {
        "messages": messages,
        "temperature": float(AZURE_OPENAI_TEMPERATURE),
        "max_tokens": 10000,
        "top_p": float(AZURE_OPENAI_TOP_P),
        # "stop": None,
        "dataSources": data_sources
    }

    max_retries = 3
    retries = 0
    def log_error_to_file(message: str):
        
        with open("err_log.txt", "a", encoding="utf-8") as f:
            timestamp = dt.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")

    while retries <= max_retries:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(BASE_URL, headers=headers, json=body)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code >= 400 and response.status_code < 500:
                    log_error_to_file(f"Received {response.status_code} from Azure OpenAI: {response.text}. Retrying {retries+1}/{max_retries}...")
                    retries += 1
                    if retries > max_retries:
                        log_error_to_file(f"Azure OpenAI returned 400 after {max_retries} retries: {response.text}")
                        raise HTTPException(status_code=400, detail=f"Azure OpenAI returned 400 after {max_retries} retries: {response.text}")
                    await asyncio.sleep(10)
                else:
                    log_error_to_file(f"Error from Azure OpenAI: {response.status_code} - {response.text}")
                    raise HTTPException(status_code=response.status_code, detail=f"Error from Azure OpenAI: {response.text}")
        except (httpx.ReadTimeout, httpx.TimeoutException, asyncio.TimeoutError) as e:
            log_error_to_file(f"Timeout error: {str(e)}. Retrying {retries+1}/{max_retries}...")
            retries += 1
            if retries > max_retries:
                log_error_to_file(f"Timeout after {max_retries} retries: {str(e)}")
                raise HTTPException(status_code=504, detail=f"Timeout after {max_retries} retries: {str(e)}")
            await asyncio.sleep(10)
        except Exception as e:
            log_error_to_file(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

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
    # proposals = request.json
    combined_content = []

    for p in proposals:
        blob_client = blob_service_client.get_blob_client(
            container=PROPOSAL_TEMPLATE_CONTAINER_NAME,
            blob='templates/' + p.proposal.name
        )
        blob_bytes = blob_client.download_blob().readall()
        
        # Load the Word document from bytes
        doc = Document(io.BytesIO(blob_bytes))

        # Extract all text
        text = get_all_text_from_doc(doc)
        
        combined_content.append(text)
    return combined_content

async def generate_proposal(conversation_id: UUID, db: Session, uid: UUID):
    current_user = db.query(User).filter_by(id=uid).first()
    messages = (
        db.query(Message.content)
        .filter(
            Message.user_id == uid,
            Message.conversation_id == conversation_id
        )
        .order_by(asc(Message.created_at))
        .all()
    )
    if not messages:
        raise ValueError(f"No messages found for conversation {conversation_id}")
    
    message_contents = [m[0] for m in messages]
    question_categories = db.query(ProposalQuestions.category)\
                            .order_by(asc(ProposalQuestions.id))\
                            .all()
    question_categories = [row.category for row in question_categories]
    
    questions = [{"category": question_categories[i].value if i < len(question_categories) else "General", "content": x} for i, x in enumerate(message_contents[::2])]
    answers = message_contents[1::2]  
    user_input = input_parser(questions, answers)
    proposal_metadata = [
        ProposalMetadataSchema.model_validate(row)
        for row in db.query(ProposalMetadata).all()
    ]

    sections = ['BusinessContext', 'Understanding', 'Objectives', 'Deliverables', 'Approach', 'Outcomes', 'CaseStudies', 'Commercials']
    
    top_proposals = get_n_matching_proposals(user_input, proposal_metadata)
    qa_prompt_string = ''.join([f"{message_contents[i]}\n{message_contents[i+1]}\n\n" for i in range(0, len(message_contents)-1, 2) if i+1 < len(message_contents)])

    proposal_content= get_proposal_content(top_proposals)
    agg_proposal_content = ""
    for c in range(len(proposal_content)):
        agg_proposal_content += f"Proposal document content {c+1}:\n\n" + proposal_content[c] + "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"

    tasks = []
    for section in sections:        
        section_pre_prompt = get_section_prompts(section)

        if section in ['CaseStudies', 'Commercials']: # static sections
            llm_text = f"""
{section_pre_prompt}
"""
        else:
            start_tag = f"SECTION_{section.upper()}_START"
            end_tag = f"SECTION_{section.upper()}_END"
            if start_tag in agg_proposal_content and end_tag in agg_proposal_content:
                # Build regex pattern (non-greedy, DOTALL to match across lines)
                pattern = re.compile(
                    re.escape(start_tag) + r"(.*?)" + re.escape(end_tag),
                    re.DOTALL
                )

                matches = pattern.findall(agg_proposal_content)

                if matches:
                    labelled_proposal_content = "\n".join(
                        f"EXAMPLE CONTENT {i+1} : {m.strip()}"
                        for i, m in enumerate(matches)
                    )
                else:
                    labelled_proposal_content = agg_proposal_content
            else:
                labelled_proposal_content = agg_proposal_content
            llm_text = f"""
{section_pre_prompt}

Input Q&A:
{qa_prompt_string}

Best in class proposal document content:
{labelled_proposal_content}
"""

        tasks.append(fetch_chat_completion(llm_text, AI_PROPOSAL_SYSTEM_PROMPT, DOCS_PROMPT, conversation_id))

    # Process results and handle exceptions
    formatted = []

    # # Business context section alone needs to be pulled from web
    # company_name = message_contents[1] # 1st Q/A pair is company name
    # business_context = get_company_info(company_name)
    # formatted.append({"prompt": "BusinessContext", "response": business_context})

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            formatted.append({"prompt": sections[i], "error": str(result)})
        else:
            # choice = ''.join([msg["content"] for msg in result["choices"][0]["messages"] if msg["role"] == "assistant"])
            choice = result["choices"][0]["messages"][1]["content"] # messages[0] is tool messages[1] is assistant
            formatted.append({"prompt": sections[i], "response": choice})

    llm_success_responses = "\n\n".join(
        item["response"] for item in formatted if "response" in item
    )

    # Store generated proposal to DB before sending to frontend
    first_message = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        .scalars()
        .first()
    )

    # Precompute created_at timestamps
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = datetime.timedelta(milliseconds=1)
    created_at_assistant = now
    created_at_tool = now + delta

    new_message = Message(
        user_id=first_message.user_id,
        conversation_id=conversation_id,
        workspace_id=first_message.workspace_id,
        content=llm_success_responses,
        role="assistant",
        model_type="",
        chat_type="hybrid",
        input_tokens=0,
        output_tokens=0,
        created_at=created_at_assistant
    )

    # Adding top referred proposals as role:tool message
    citations = {"citations": [{"filepath": p.proposal.name, "url": p.proposal.link} for p in top_proposals]}

    reference_proposals = Message(
        user_id=first_message.user_id,
        conversation_id=conversation_id,
        workspace_id=first_message.workspace_id,
        content=json.dumps(citations),
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
    try:
        proposal_docx_upload(llm_success_responses, current_user.email, conversation_id)
    except Exception as e:
        print(f"Warning: Could not upload to blob storage: {e}")
    return {"proposal": formatted, "citations": citations}

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


async def edit_proposal_service(conversation_id: UUID, recent_message: str, new_message: str, db: Session, current_user: User):
    
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
        assistant_content = llm_response["choices"][0]["messages"][1]["content"]
        tool_content = llm_response["choices"][0]["messages"][0]["content"]
        
        last_message = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at.desc()).first()
        if not last_message:
            return {"message": "No message found to update"}
        
        # Precompute created_at timestamps
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = datetime.timedelta(milliseconds=1)
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
        # Update existing assistant message
        last_assistant_message = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.role == "assistant"
        ).order_by(Message.created_at.desc()).first()
        
        if last_assistant_message:
            last_assistant_message.content = assistant_content
        db.add(assistant_msg)
        db.add(tool_msg)
        db.commit()
        
        return {"assistant": assistant_content, "tool": tool_content}
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
    q_count = db.query(ProposalQuestions).count()
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(asc(Message.created_at))
        .all()
    )
    if len(messages) <= q_count * 2:
        raise HTTPException(status_code=404, detail="Not enough messages to generate proposal document.")
    if messages[-1].role == 'tool':
        last_proposal_content = messages[-2].content
    else:
        raise HTTPException(status_code=404, detail="Last message does not have role='tool'.")

    # Fetch DOCX template from Azure Blob
    blob_name = "template.docx"
    blob_client = blob_service_client.get_blob_client(
        container=PROPOSAL_TEMPLATE_CONTAINER_NAME,
        blob='templates/' + blob_name
    )
    blob_data = blob_client.download_blob().readall()

    # Load template
    doc = Document(io.BytesIO(blob_data))

    add_content_to_doc(doc, last_proposal_content)

    # Save modified DOCX in memory
    doc_stream = io.BytesIO()
    doc.save(doc_stream)
    doc_stream.seek(0)

    # Return the DOCX file as a streaming response
    return StreamingResponse(
        doc_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": "attachment; filename=generated_proposal.docx"
        }
    )

def proposal_docx_upload(proposal_content: str, user_email: str, conversation_id: UUID):
    # Fetch DOCX template from Azure Blob
    blob_name = "template.docx"
    blob_client = blob_service_client.get_blob_client(
        container=PROPOSAL_TEMPLATE_CONTAINER_NAME,
        blob='templates/' + blob_name
    )
    blob_data = blob_client.download_blob().readall()

    # Load template
    doc = Document(io.BytesIO(blob_data))

    add_content_to_doc(doc, proposal_content)
    # Save modified DOCX in memory
    doc_stream = io.BytesIO()
    doc.save(doc_stream)
    doc_stream.seek(0)

    # Create a new BlobServiceClient for GENERATED_PROPOSALS_CONTAINER_NAME container
    generated_blob_service_client = BlobServiceClient.from_connection_string(
        os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
    )
    generated_blob_client = generated_blob_service_client.get_blob_client(
        container=GENERATED_PROPOSALS_CONTAINER_NAME,
        blob=f"{user_email}/{user_email}----{conversation_id}----generated_proposal_{uuid.uuid4()}.docx"
    )
    generated_blob_client.upload_blob(doc_stream, overwrite=True)

    
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
    blob_service_client = AsyncBlobServiceClient.from_connection_string(
        os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
    )
    container_client = blob_service_client.get_container_client(AI_PROPOSAL_WORKSPACE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(blob_path)

    await blob_client.upload_blob(file, overwrite=True)
