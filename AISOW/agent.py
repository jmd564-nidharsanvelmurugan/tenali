import os
import json
from langchain_openai import AzureChatOpenAI
from langchain.agents.agent import AgentExecutor
from langchain.agents import create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import HumanMessage, AIMessage
from AISOW.tools import facet_count, filter_titles, semantic_search, fetch_summaries

SYSTEM_PROMPT = """You are an AI assistant for the AISOW knowledge base at JMAN Group.
You have access to a database of Statement of Work (SOW) documents with structured metadata.

You have 4 tools:
1. facet_count — for counting/grouping questions (how many, list all domains, count by type)
2. filter_titles — for listing SOW titles matching a domain/client/project_type/platform
3. fetch_summaries — for summarizing or getting overview of MULTIPLE SOWs (uses pre-extracted summaries, scales to hundreds of SOWs)
4. semantic_search — for deep-dive content questions on a SPECIFIC SOW (summarize one SOW, problem statement, technologies used)

Rules:
- Always use tools — never answer from memory alone
- For counting questions about a specific domain/client/type: use filter_titles to get exact unique document count
- For overall breakdown across all domains/clients: use facet_count (approximate chunk counts)
- For listing titles only: use filter_titles
- For summarizing/overview of multiple SOWs: use fetch_summaries (NOT semantic_search)
- For deep content on a specific single SOW: use semantic_search
- Always list ALL results from filter_titles — never truncate or say "here are some"
- You can call multiple tools in sequence to build a complete answer
- Be precise with counts — use the exact numbers from tool results
- Cite source document titles when referencing specific SOWs

IMPORTANT — When using filter_titles:
- Use SHORT keyword values for single domain searches
- CORRECT: filter_titles("domains:AI/ML") — finds all SOWs where domains contains "AI/ML"
- WRONG: filter_titles("domains:AI/ML, Data Analytics, Data Engineering") — too specific, misses many SOWs
- The domains field contains comma-separated values — search by ONE keyword at a time
- EXCEPTION: If the user explicitly asks for SOWs matching MULTIPLE specific domains together
  (e.g. "SOWs that have both AI/ML AND Cloud Infrastructure"), then call filter_titles multiple times
  (once per domain) and find the intersection yourself
"""


def build_agent() -> AgentExecutor:
    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL_NAME_1"),
        api_version="2023-06-01-preview",
        temperature=0,
        streaming=True,
    )

    tools = [facet_count, filter_titles, semantic_search, fetch_summaries]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=10, handle_parsing_errors=True, return_intermediate_steps=True)


def convert_history(prior_messages: list[dict]) -> list:
    """Convert prior conversation messages to LangChain message objects."""
    history = []
    for m in prior_messages:
        if m["role"] == "user":
            history.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            history.append(AIMessage(content=m["content"]))
    return history


async def run_aisow_agent(question: str, prior_messages: list[dict]):
    """
    Async generator — yields text tokens then a citations_ready event if semantic_search was used.
    """
    agent = build_agent()
    history = convert_history(prior_messages)

    import asyncio
    loop = asyncio.get_event_loop()
    result = await asyncio.wait_for(
        loop.run_in_executor(None, lambda: agent.invoke({"input": question, "chat_history": history})),
        timeout=180.0  # 3 minutes
    )

    answer = result.get("output", "")

    # Stream answer tokens
    for token in answer.split(" "):
        yield token + " "

    # Extract citations from tool calls in intermediate_steps
    steps = result.get("intermediate_steps", [])
    citations = []
    for action, observation in steps:
        if not hasattr(action, "tool") or not observation:
            continue

        if action.tool == "semantic_search":
            import re
            blocks = re.split(r'\[\d+\]', observation)
            all_chunks = []
            for block in blocks:
                if not block.strip():
                    continue
                title = re.search(r'Title:\s*(.+)', block)
                content = re.search(r'Content:\s*([\s\S]+)', block)
                url = re.search(r'URL:\s*(.+)', block)
                t = title.group(1).strip() if title else ""
                if t:
                    all_chunks.append({
                        "title": t,
                        "filepath": t,
                        "content": content.group(1).strip()[:1000] if content else "",
                        "url": url.group(1).strip() if url else "",
                    })

            # Only keep chunks from docs actually mentioned in the final answer
            answer_lower = answer.lower()
            common_words = {'jman', 'group', 'client', 'statement', 'work', 'design', 'discovery', 'draft', 'limited', 'services', 'agreement'}
            relevant = [c for c in all_chunks if any(
                w.lower() in answer_lower 
                for w in c["title"].replace(".docx","").replace("_"," ").split() 
                if len(w) > 3 and w.lower() not in common_words
            )]
            citations.extend(relevant[:5])

        elif action.tool == "filter_titles":
            import re
            for line in observation.splitlines():
                if line.startswith("- "):
                    parts = line[2:].split(" | ")
                    title = parts[0].strip()
                    # Only include if title is mentioned in the answer
                    title_words = [w.lower() for w in title.replace(".docx","").replace("_"," ").split() if len(w) > 4]
                    if any(w in answer.lower() for w in title_words):
                        url = next((p.replace("URL:", "").strip() for p in parts if p.startswith("URL:")), "")
                        citations.append({
                            "title": title,
                            "filepath": title,
                            "content": " | ".join(p for p in parts[1:] if not p.startswith("URL:")),
                            "url": url,
                        })

    # Cap total citations at 5
    citations = citations[:5]

    if citations:
        yield "CITATIONS_PAYLOAD:" + json.dumps({"type": "citations_ready", "citations": citations})
