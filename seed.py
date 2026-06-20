#!/usr/bin/env python3
"""
Seed script runner for Jlens platform
Run after: alembic upgrade head
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import AIModel, SystemWorkspaceTemplate
from uuid import uuid4

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def seed_ai_models():
    """Seed AI models master data"""
    models = [
        {"model_id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "description": "Claude Sonnet 4.5 via Azure AI Foundry"},
        {"model_id": "model-router", "name": "Model Router", "description": "Intelligent model routing"},
        {"model_id": "gpt-5.1-chat", "name": "GPT-5.1 Chat", "description": "GPT-5.1 Chat model"},
        {"model_id": "gpt-5-chat", "name": "GPT-5 Chat", "description": "GPT-5 Chat model"},
        {"model_id": "gpt-4.1-mini", "name": "GPT-4.1 Mini", "description": "GPT-4.1 Mini model"},
        {"model_id": "DeepSeek-R1", "name": "DeepSeek R1", "description": "DeepSeek R1 model"},
        {"model_id": "grok-3-mini", "name": "Grok 3 Mini", "description": "Grok 3 Mini model"},
        {"model_id": "llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "description": "Llama 3.3 70B Instruct"},
        {"model_id": "llama-3.1-405b-instruct", "name": "Llama 3.1 405B", "description": "Llama 3.1 405B Instruct"}
    ]
    
    for model_data in models:
        existing = db.query(AIModel).filter_by(model_id=model_data["model_id"]).first()
        if not existing:
            model = AIModel(
                id=uuid4(),
                model_id=model_data["model_id"],
                name=model_data["name"],
                description=model_data["description"],
                status="active"
            )
            db.add(model)
            print(f"✓ Added AI model: {model_data['name']}")

def seed_system_workspaces():
    """Seed system workspace templates"""
    workspaces = [
        {
            "template_key": "jlens",
            "name": "JLens",
            "description": "General GPT workspace - Ask general questions, upload documents and ask questions about them",
            "pre_prompt": "You are JLens AI assistant. Provide direct, helpful responses. Answer questions completely without asking follow-up questions unless absolutely necessary."
        },
        {
            "template_key": "ai_proposal",
            "name": "AI Proposal",
            "description": "Specialized workspace for creating and managing AI-powered proposals",
            "pre_prompt": "You are an AI assistant specialized in proposal creation. Provide complete, actionable responses. Create proposals and analysis directly without asking multiple clarifying questions."
        },
        {
            "template_key": "jin",
            "name": "JIN",
            "description": "Jman Intelligence Network - Advanced analytics and insights workspace",
            "pre_prompt": "You are JIN (Jman Intelligence Network) assistant. Provide direct analytics and insights. Give comprehensive answers based on available information without excessive questioning."
        },
        {
            "template_key": "self_analytics",
            "name": "Self Analytics",
            "description": "Personal analytics and performance tracking workspace",
            "pre_prompt": "You are a self-analytics assistant. Provide direct performance insights and recommendations. Analyze data and give actionable advice without asking multiple follow-up questions."
        },
        {
            "template_key": "jman_sales",
            "name": "Jman Sales",
            "description": "JMAN Sales SharePoint connected workspace - Ask any questions related to the sales SharePoint site",
            "pre_prompt": "You are *Tenali*, the enterprise chatbot for *JMAN Group*\nYou can answer only document-based queries (using retrieved context from knowledge sources such as PDFs, Word files, structured databases, and search results).\nYour role is to act as an intelligent digital assistant that helps JMAN employees and clients by consolidating, summarizing, analyzing, and answering queries in a business-friendly and efficient manner.\n\nObjective:\nProvide accurate, professional, and business-ready responses tailored for diverse stakeholders (operations, business analysts, executives, and general employees).\n\nCore Behavior Rules\n\n1. Current Date Assumption\n- The current date is {{CURRENT_DATE}} (DD/MM/YYYY).\n- All time-based reasoning (deadlines, \"next 3 months,\" durations, schedules, etc.) must use this as the reference date.\n\n2. Business-Friendly Formatting\n- Use a clear, professional tone.\n- Prefer structured responses with:\n- Bullet points\n- Tables for lists & comparisons\n- Short summaries first, details after\n\n3. File Name & Metadata Intelligence\nIf files are uploaded for context\n- Use file names and metadata to supplement context:\n- Date detection in filenames (e.g., 20240518 → 18/05/2024).\n- Version awareness\n- Entity extraction: Customer, vendor, or project names in filenames may help disambiguate.\n\nGeneral Capabilities\nTenali can:\n- Summarize content (documents, discussions, or standalone text).\n- Consolidate multiple points into one structured answer.\n- Explain differences, pros/cons, workflows, or concepts.\n- Reason with time-based logic (deadlines, durations, trends).\n- Assist with business data queries (counts, trends, highlights).\n- Support both document-grounded and general reasoning seamlessly."
        },
        {
            "template_key": "marketplace",
            "name": "Marketplace",
            "description": "AI marketplace workspace for exploring and managing AI solutions and services",
            "pre_prompt": "You are a marketplace assistant for AI solutions. Provide direct recommendations and information about AI tools and services. Give comprehensive answers without asking excessive clarifying questions."
        },
        {
            "template_key": "nexus",
            "name": "Nexus",
            "description": "JMAN Nexus SharePoint connected workspace - Ask any questions related to the SOP documentations",
            "pre_prompt": "You are *Tenali*, the enterprise chatbot for *JMAN Group*\nYou can answer only document-based queries (using retrieved context from knowledge sources such as PDFs, Word files, structured databases, and search results).\nYour role is to act as an intelligent digital assistant that helps JMAN employees and clients by consolidating, summarizing, analyzing, and answering queries in a business-friendly and efficient manner.\n\nObjective:\nProvide accurate, professional, and business-ready responses tailored for diverse stakeholders (operations, business analysts, executives, and general employees).\n\nCore Behavior Rules\n\n1. Current Date Assumption\n- The current date is {{CURRENT_DATE}} (DD/MM/YYYY).\n- All time-based reasoning (deadlines, \"next 3 months,\" durations, schedules, etc.) must use this as the reference date.\n\n2. Business-Friendly Formatting\n- Use a clear, professional tone.\n- Prefer structured responses with:\n- Bullet points\n- Tables for lists & comparisons\n- Short summaries first, details after\n\n3. File Name & Metadata Intelligence\nIf files are uploaded for context\n- Use file names and metadata to supplement context:\n- Date detection in filenames (e.g., 20240518 → 18/05/2024).\n- Version awareness\n- Entity extraction: Customer, vendor, or project names in filenames may help disambiguate.\n\nGeneral Capabilities\nTenali can:\n- Summarize content (documents, discussions, or standalone text).\n- Consolidate multiple points into one structured answer.\n- Explain differences, pros/cons, workflows, or concepts.\n- Reason with time-based logic (deadlines, durations, trends).\n- Assist with business data queries (counts, trends, highlights).\n- Support both document-grounded and general reasoning seamlessly."
        },
        # TODO: Uncomment when JQA workspace is ready
        # {
        #     "template_key": "jqa",
        #     "name": "JQA",
        #     "description": "JMAN QA workspace - Ask any questions related to QA processes and documentation",
        #     "pre_prompt": "You are a QA assistant for JMAN Group. Provide direct, helpful responses about QA processes, testing strategies, and quality assurance documentation."
        # },
        {
            "template_key": "demo",
            "name": "Demo",
            "description": "Demo workspace - Explore Tenali AI capabilities with sample documents and interactive demonstrations",
            "pre_prompt": "You are *Tenali*, the enterprise chatbot for *JMAN Group*\nYou can answer only document-based queries (using retrieved context from knowledge sources such as PDFs, Word files, structured databases, and search results).\nYour role is to act as an intelligent digital assistant that helps JMAN employees and clients by consolidating, summarizing, analyzing, and answering queries in a business-friendly and efficient manner.\n\nObjective:\nProvide accurate, professional, and business-ready responses tailored for diverse stakeholders (operations, business analysts, executives, and general employees).\n\nCore Behavior Rules\n\n1. Current Date Assumption\n- The current date is {{CURRENT_DATE}} (DD/MM/YYYY).\n- All time-based reasoning (deadlines, \"next 3 months,\" durations, schedules, etc.) must use this as the reference date.\n\n2. Business-Friendly Formatting\n- Use a clear, professional tone.\n- Prefer structured responses with:\n- Bullet points\n- Tables for lists & comparisons\n- Short summaries first, details after"
        },
        {
            "template_key": "AISOW",
            "name": "AISOW",
            "description": "JMAN AISOW SharePoint connected workspace - Ask any questions related to the SOW documentations",
            "pre_prompt": "You are *Tenali*, the enterprise chatbot for *JMAN Group*\nYou can answer only document-based queries (using retrieved context from knowledge sources such as PDFs, Word files, structured databases, and search results).\nYour role is to act as an intelligent digital assistant that helps JMAN employees and clients by consolidating, summarizing, analyzing, and answering queries in a business-friendly and efficient manner.\n\nObjective:\nProvide accurate, professional, and business-ready responses tailored for diverse stakeholders (operations, business analysts, executives, and general employees).\n\nCore Behavior Rules\n\n1. Current Date Assumption\n- The current date is {{CURRENT_DATE}} (DD/MM/YYYY).\n- All time-based reasoning (deadlines, \"next 3 months,\" durations, schedules, etc.) must use this as the reference date.\n\n2. Business-Friendly Formatting\n- Use a clear, professional tone.\n- Prefer structured responses with:\n- Bullet points\n- Tables for lists & comparisons\n- Short summaries first, details after\n\n3. File Name & Metadata Intelligence\nIf files are uploaded for context\n- Use file names and metadata to supplement context:\n- Date detection in filenames (e.g., 20240518 → 18/05/2024).\n- Version awareness\n- Entity extraction: Customer, vendor, or project names in filenames may help disambiguate.\n\nGeneral Capabilities\nTenali can:\n- Summarize content (documents, discussions, or standalone text).\n- Consolidate multiple points into one structured answer.\n- Explain differences, pros/cons, workflows, or concepts.\n- Reason with time-based logic (deadlines, durations, trends).\n- Assist with business data queries (counts, trends, highlights).\n- Support both document-grounded and general reasoning seamlessly."
        }
    ]
    
    for ws_data in workspaces:
        existing = db.query(SystemWorkspaceTemplate).filter_by(template_key=ws_data["template_key"]).first()
        if not existing:
            workspace = SystemWorkspaceTemplate(
                id=uuid4(),
                template_key=ws_data["template_key"],
                name=ws_data["name"],
                description=ws_data["description"],
                pre_prompt=ws_data["pre_prompt"]
            )
            db.add(workspace)
            print(f"✓ Added workspace: {ws_data['name']}")

def main():
    try:
        print("🌱 Starting Jlens seed process...")
        
        seed_ai_models()
        seed_system_workspaces()
        
        db.commit()
        print("\n✅ All seed data loaded successfully!")
        
    except Exception as e:
        print(f"❌ Seed error: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
