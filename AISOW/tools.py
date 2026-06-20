import os
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from langchain.tools import tool

SEARCH_SERVICE = os.getenv("AZURE_SEARCH_SERVICE")
SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
INDEX = "tenaliaz-aisow-index"


def set_index(index_name: str):
    global INDEX
    INDEX = index_name


def _client() -> SearchClient:
    return SearchClient(
        endpoint=f"https://{SEARCH_SERVICE}.search.windows.net",
        index_name=INDEX,
        credential=AzureKeyCredential(SEARCH_KEY),
    )


@tool
def facet_count(question: str) -> str:
    """
    Use this tool when the user asks aggregation questions like:
    'how many AI SOWs', 'list all domains', 'how many clients', 'count by project type'.
    Returns counts of all unique values for domains, client, project_type, platform fields.
    Also returns the total number of unique SOW documents (not chunks).
    NOTE: domain/client counts are chunk-based approximations. For exact unique document counts
    per domain, use filter_titles after this tool.
    """
    client = _client()
    try:
        results = client.search(
            search_text="*",
            facets=["title,count:10000", "domains,count:1000", "client,count:1000", "project_type,count:1000", "platform,count:1000"],
            top=0,
        )
        facets = results.get_facets() or {}
    except Exception as e:
        return f"Error querying index: {str(e)}"

    # Unique SOW count = unique titles (not total chunks)
    unique_sows = len(facets.get("title", []))
    output = [f"Total unique SOW documents: {unique_sows}\n"]
    output.append("NOTE: counts below are approximate (chunk-based). Use filter_titles for exact unique document counts.\n")

    for field in ["domains", "client", "project_type", "platform"]:
        values = facets.get(field, [])
        if values:
            output.append(f"\n{field.upper()}:")
            for v in values:
                output.append(f"  - {v['value']}: ~{v['count']} chunks")
    return "\n".join(output)


@tool
def filter_titles(field_and_value: str) -> str:
    """
    Use this tool to get all SOW titles matching a specific domain, client, project_type or platform.
    Input format: 'field:value' e.g. 'domains:AI' or 'client:Ashtons' or 'project_type:Managed Service'
    Returns list of matching SOW titles with client names.
    """
    try:
        field, value = field_and_value.split(":", 1)
        field, value = field.strip(), value.strip()
    except ValueError:
        return "Invalid input. Use format 'field:value' e.g. 'domains:AI'"

    client = _client()
    # searchable fields: use search.ismatch for partial/contains match
    searchable_fields = {"domains", "client", "platform", "title", "sharepoint_name", "subdomains"}
    if field in searchable_fields:
        # Use partial match — searches within the field value
        filter_expr = f"search.ismatch('\"{value}\"', '{field}')"
    else:
        filter_expr = f"{field} eq '{value}'"

    results = client.search(
        search_text="*",
        filter=filter_expr,
        select=["title", "client", "domains", "project_type", "summary", "sharepoint_url"],
        top=1000,
    )
    seen, rows = set(), []
    for r in results:
        t = r.get("title", "").strip()
        if t and t not in seen:
            seen.add(t)
            rows.append(f"- {t} | Client: {r.get('client','')} | Type: {r.get('project_type','')} | URL: {r.get('sharepoint_url','')}")

    if not rows:
        return f"No SOWs found where {field} matches '{value}'"
    return f"Found {len(rows)} SOWs where {field} = '{value}':\n" + "\n".join(rows)


@tool
def semantic_search(query: str) -> str:
    """
    Use this tool for specific content questions like:
    'what is the problem statement of X SOW', 'summarize Colonis SOW',
    'what technologies does Ashtons use', 'give overview of project Y'.
    Returns relevant document chunks with metadata.
    """
    from Jlens.lib.azure_search_service import AzureSearchService
    chunks = AzureSearchService().search_documents_hybrid(
        query=query, workspace_name="AISOW", index_name=INDEX, top=10
    )
    if not chunks:
        return "No relevant documents found."

    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[{i}] Title: {c.get('title','')}\n"
            f"    Client: {c.get('client','')}\n"
            f"    Domains: {c.get('domains','')}\n"
            f"    URL: {c.get('sharepoint_url','')}\n"
            f"    Summary: {c.get('summary','')}\n"
            f"    Content: {(c.get('chunk') or '')[:800]}"
        )
    return "\n\n".join(parts)


@tool
def fetch_summaries(field_and_value: str) -> str:
    """
    Use this tool when the user asks to summarize, compare, or get an overview of MULTIPLE SOWs
    matching a domain, client, project_type, or platform.
    Examples: "summarize all AI SOWs", "overview of all managed service projects",
              "what are all the cloud SOWs about", "compare all LLM projects"
    Input format: 'field:value' e.g. 'domains:AI/ML' or 'project_type:Managed Service'
    Returns title + client + pre-extracted summary for every matching SOW — lightweight, fits in context.
    """
    try:
        field, value = field_and_value.split(":", 1)
        field, value = field.strip(), value.strip()
    except ValueError:
        return "Invalid input. Use format 'field:value' e.g. 'domains:AI/ML'"

    client = _client()
    searchable_fields = {"domains", "client", "platform", "title", "sharepoint_name", "subdomains"}
    filter_expr = (
        f"search.ismatch('\"{value}\"', '{field}')"
        if field in searchable_fields
        else f"{field} eq '{value}'"
    )

    results = client.search(
        search_text="*",
        filter=filter_expr,
        select=["title", "client", "project_type", "domains", "summary", "sharepoint_url"],
        top=1000,
    )

    seen, rows = set(), []
    for r in results:
        t = r.get("title", "").strip()
        if t and t not in seen:
            seen.add(t)
            rows.append(
                f"- {t}\n"
                f"  Client: {r.get('client', '')}\n"
                f"  Type: {r.get('project_type', '')}\n"
                f"  Summary: {r.get('summary', 'No summary available')}"
            )

    if not rows:
        return f"No SOWs found where {field} matches '{value}'"
    return f"Found {len(rows)} SOWs where {field} = '{value}':\n\n" + "\n\n".join(rows)
