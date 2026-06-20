import io
import re
import time
import time
import uuid
import datetime
from fastapi.responses import StreamingResponse
import requests
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
import datetime
from datetime import datetime as dt

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
        async with AsyncBlobServiceClient.from_connection_string(
            os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        ) as blob_service_client:
            container_client = blob_service_client.get_container_client(AI_PROPOSAL_SALES_QAS_CONTAINER_NAME)
            blob_name = f"{user_id}----{conversation_id}.docx"
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
    """Reads the uploaded sales call questions DOCX file with proper async context management"""
    blob_name = f"{user_id}----{conversation_id}.docx"
    try:
        async with AsyncBlobServiceClient.from_connection_string(
            os.environ.get("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        ) as blob_service_client:
            blob_client = blob_service_client.get_blob_client(
                container=AI_PROPOSAL_SALES_QAS_CONTAINER_NAME,
                blob=blob_name
            )
            blob_bytes = await (await blob_client.download_blob()).readall()
            doc = Document(io.BytesIO(blob_bytes))
            text = get_all_text_from_doc(doc)
            return text
    except Exception as e:
        print(f"Warning: Could not read sales Q&A file: {e}")
        return ""



















# async def generate_proposal(conversation_id: UUID, db: Session, uid: UUID):


#     current_user = db.query(User).filter_by(id=uid).first()



#     messages = (
#         db.query(Message.content)
#         .filter(
#             Message.user_id == uid,
#             Message.conversation_id == conversation_id
#         )
#         .order_by(asc(Message.created_at))
#         .all()
#     )
    

#     print("$" * 100)
#     print(f"Fetched {len(messages)} messages for conversation {conversation_id} and user {uid}")
#     print("$" * 100)

#     if not messages:
#         raise ValueError(f"No messages found for conversation {conversation_id}")
    

#     message_contents = [m[0] for m in messages]




#     question_categories = db.query(ProposalQuestions.category)\
#                             .order_by(asc(ProposalQuestions.id))\
#                             .all()
#     question_categories = [row.category for row in question_categories]
    
#     questions = [{"category": question_categories[i].value if i < len(question_categories) else "General", "content": x} for i, x in enumerate(message_contents[::2])]
#     answers = message_contents[1::2]  
#     user_input = input_parser(questions, answers)
#     proposal_metadata = [
#         ProposalMetadataSchema.model_validate(row)
#         for row in db.query(ProposalMetadata).all()
#     ]

#     sections = ['BusinessContext', 'Understanding', 'Objectives', 'Deliverables', 'Approach', 'Outcomes', 'CaseStudies', 'Commercials']
    
#     top_proposals = get_n_matching_proposals(user_input, proposal_metadata)
#     client_context_qas = await read_uploaded_sales_call_questions_docx(uid, conversation_id)
#     matrix_qas = ""
#     for i in range(0, len(message_contents), 2):
#         # Skip if category is 'GENERAL' or first Q/A pair (i == 0)
#         if questions[i//2]['category'] != 'GENERAL' or i == 0:
#             matrix_qas += f"{message_contents[i]}\n{message_contents[i+1]}\n\n"
            

#     proposal_content= get_proposal_content(top_proposals)
#     agg_proposal_content = ""
#     for c in range(len(proposal_content)):
#         agg_proposal_content += f"Proposal document content {c+1}:\n\n" + proposal_content[c] + "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"

#     tasks = []
#     for section in sections:        
#         section_pre_prompt = get_section_prompts(section)

#         if section in ['CaseStudies', 'Commercials']: # static sections
#             llm_text = f"""
# {section_pre_prompt}
# """
#         else:
#             start_tag = f"SECTION_{section.upper()}_START"
#             end_tag = f"SECTION_{section.upper()}_END"
#             if start_tag in agg_proposal_content and end_tag in agg_proposal_content:
#                 # Build regex pattern (non-greedy, DOTALL to match across lines)
#                 pattern = re.compile(
#                     re.escape(start_tag) + r"(.*?)" + re.escape(end_tag),
#                     re.DOTALL
#                 )

#                 matches = pattern.findall(agg_proposal_content)

#                 if matches:
#                     labelled_proposal_content = "\n".join(
#                         f"EXAMPLE CONTENT {i+1} : {m.strip()}"
#                         for i, m in enumerate(matches)
#                     )
#                 else:
#                     labelled_proposal_content = agg_proposal_content
#             else:
#                 labelled_proposal_content = agg_proposal_content
#             llm_text = f"""
# {section_pre_prompt}

# Input Q&A:
# {matrix_qas}

# Client context Q&A:
# {client_context_qas}

# Best in class proposal document content:
# {labelled_proposal_content}
# """

#         tasks.append(fetch_chat_completion(llm_text, AI_PROPOSAL_SYSTEM_PROMPT, DOCS_PROMPT, conversation_id))

#     # Process results and handle exceptions
#     formatted = []

#     # # Business context section alone needs to be pulled from web
#     # company_name = message_contents[1] # 1st Q/A pair is company name
#     # business_context = get_company_info(company_name)
#     # formatted.append({"prompt": "BusinessContext", "response": business_context})

#     results = await asyncio.gather(*tasks, return_exceptions=True)

#     for i, result in enumerate(results):
#         if isinstance(result, Exception):
#             formatted.append({"prompt": sections[i], "error": str(result)})
#         else:
#             try:
#                 # Standard OpenAI response format
#                 choice = result["choices"][0]["message"]["content"]
#                 formatted.append({"prompt": sections[i], "response": choice})
#             except (KeyError, IndexError) as e:
#                 formatted.append({"prompt": sections[i], "error": f"Response parsing error: {e}"})

#     llm_success_responses = "\n\n".join(
#         item["response"] for item in formatted if "response" in item
#     )

#     # Store generated proposal to DB before sending to frontend
#     first_message = (
#         db.execute(
#             select(Message)
#             .where(Message.conversation_id == conversation_id)
#             .order_by(Message.created_at.asc())
#         )
#         .scalars()
#         .first()
#     )

#     # Precompute created_at timestamps
#     now = datetime.datetime.now(datetime.timezone.utc)
#     delta = datetime.timedelta(milliseconds=1)
#     created_at_assistant = now
#     created_at_tool = now + delta

#     new_message = Message(
#         user_id=first_message.user_id,
#         conversation_id=conversation_id,
#         workspace_id=first_message.workspace_id,
#         content=llm_success_responses,
#         role="assistant",
#         model_type="",
#         chat_type="hybrid",
#         input_tokens=0,
#         output_tokens=0,
#         created_at=created_at_assistant
#     )

#     # Adding top referred proposals as role:tool message
#     citations = {"citations": [{"filepath": p.proposal.name, "url": p.proposal.link} for p in top_proposals]}

#     reference_proposals = Message(
#         user_id=first_message.user_id,
#         conversation_id=conversation_id,
#         workspace_id=first_message.workspace_id,
#         content=json.dumps(citations),
#         role="tool",
#         model_type="",
#         chat_type="hybrid",
#         input_tokens=0,
#         output_tokens=0,
#         created_at=created_at_tool
#     )
#     db.add(new_message)
#     db.add(reference_proposals)
#     db.commit()
#     try:
#         proposal_docx_upload(llm_success_responses, current_user.email, conversation_id)
#     except Exception as e:
#         print(f"Warning: Could not upload to blob storage: {e}")
#     return {"msg_id": new_message.id, "proposal": formatted, "citations": citations}













# $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$










async def generate_proposal(conversation_id: UUID, db: Session, uid: UUID , user_prompt: str = None):
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
    
    # 2. 🔑 RETRIEVE USER PROMPT FROM DATABASE (instead of Q&A)
    
    # 3. 🔑 RETRIEVE SALES CALL QUESTIONNAIRE FROM BLOB STORAGE

    client_context_qas = await read_uploaded_sales_call_questions_docx(uid, conversation_id)
   
    # 4. Get proposal metadata for RAG matching
    
    print(user_prompt)


    # 5. Call generate_proposal_langgraph() function with both inputs
    ggg_output = generate_proposal_langgraph(questionnaire=client_context_qas, user_prompt=user_prompt)
    

    print("Received output from generate_proposal_langgraph:")
    print(ggg_output)
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
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = datetime.timedelta(milliseconds=1)
    created_at_assistant = now
    created_at_tool = now + delta
    
    # Store assistant message with complete proposal
    new_message = Message(
        user_id=first_message.user_id,
        conversation_id=conversation_id,
        workspace_id=first_message.workspace_id,
        content=ggg_output["proposal_text"],
        role="assistant",
        model_type="",
        chat_type="hybrid",
        input_tokens=0,
        output_tokens=0,
        created_at=created_at_assistant
    )
    
    # Store citations as tool message
    citations = {"citations": ggg_output["citations"]}
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
    
    # 7. Upload proposal to blob storage
    try:
        proposal_docx_upload(ggg_output["proposal_text"], current_user.email, conversation_id)
    except Exception as e:
        print(f"Warning: Could not upload to blob storage: {e}")

        
    print("*" * 100)
    print("Proposal generation and storage completed successfully.")
    print("*" * 100)
    # 8. Return response
    return {
        "msg_id": new_message.id,
        "proposal": [
        {
            "prompt": "Executive Summary",
            "response": "This proposal addresses the client's requirements."
        },
        {
            "prompt": "Approach",
            "response": "Our approach includes data analysis and reporting."
        },
        {
            "prompt": "Outcomes",
            "response": "Improved visibility and automation."
        }
    ],
        "proposal_sections": ggg_output["sections"],
        "citations": citations
    }









def get_user_prompt(db: Session, conversation_id: UUID) -> str:
    """
    Retrieve the user's prompt from the conversation
    """
    # Try to get message with message_type = "user_prompt"
    prompt_message = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.model_type == "user_prompt",
        Message.role == "user"
    ).first()
    
    
    if prompt_message:
        return prompt_message.content
    
    # Fallback: try to get the first user message as prompt
    first_user_message = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.role == "user"
    ).order_by(asc(Message.created_at)).first()
    
    if first_user_message:
        return first_user_message.content
    
    return ""













# $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$







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
        assistant_content = llm_response["choices"][0]["message"]["content"]
        # tool_content = llm_response["choices"][0]["messages"][0]["content"]
        tool_content = json.dumps({
            "citations": []
        })
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

        # Check if container name is configured
        if not PROPOSAL_TEMPLATE_CONTAINER_NAME:
            raise HTTPException(status_code=500, detail="PROPOSAL_TEMPLATE_CONTAINER_NAME not configured")

        # Try to fetch DOCX template from Azure Blob, fallback to basic template
        try:
            blob_name = "template.docx"
            blob_client = blob_service_client.get_blob_client(
                container=PROPOSAL_TEMPLATE_CONTAINER_NAME,
                blob='templates/' + blob_name
            )
            blob_data = blob_client.download_blob().readall()
            doc = Document(io.BytesIO(blob_data))
        except Exception:
            # Fallback: create a basic document
            doc = Document()
            doc.add_heading('Proposal Document', 0)

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
    except HTTPException:
        raise
    except Exception as e:
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