import os
from dotenv import load_dotenv

from azure.identity import (
    AzureCliCredential,
    DefaultAzureCredential,
    ChainedTokenCredential,
)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AgentDefinition

load_dotenv()

AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT_PROPOSAL")
AGENT_NAME = os.getenv(
    "AZURE_AGENT_PROPOSAL",
    "ai-proposal-langgraph-agent",
)

MODEL_NAME = "gpt-5"

credential = ChainedTokenCredential(
    AzureCliCredential(),
    DefaultAzureCredential(
        exclude_interactive_browser_credential=False
    ),
)

client = AIProjectClient(
    endpoint=AZURE_ENDPOINT,
    credential=credential,
)

print(f"Checking agent: {AGENT_NAME}")

existing_agent = None

for agent in client.agents.list():
    if agent.name == AGENT_NAME:
        existing_agent = agent
        break

if existing_agent:
    print(f"Agent already exists: {AGENT_NAME}")

    print("\nVersions:")
    for version in client.agents.list_versions(AGENT_NAME):
        print(version)

    exit(0)

print("Agent not found. Creating...")

kb_tool = {
    "type": "mcp",
    "server_label": "kb-kbaiproposal-c27j4",
    "server_url": "https://cog-search-tenaliaiaz-prod-uksouth.search.windows.net/knowledgebases/kbaiproposal/mcp?api-version=2026-05-01-preview",
    "require_approval": "never",
    "project_connection_id": "kb-kbaiproposal-c27j4"
}

definition = AgentDefinition(
    {
        "kind": "prompt",
        "model": MODEL_NAME,
        "instructions": """
You are a proposal generation agent.
Analyze questionnaire input.
Retrieve knowledge.
Generate proposal sections.
Return structured output.
""",
        "reasoning": {
            "effort": "low"
        },
        "tools": [kb_tool],
    }
)

created = client.agents.create_version(
    agent_name=AGENT_NAME,
    definition=definition,
    description="Proposal CICD Agent",
)

print("Agent created successfully")
print(created)