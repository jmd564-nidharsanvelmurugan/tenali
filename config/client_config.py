# Centralized client-workspace mapping configuration

CLIENT_WORKSPACE_MAP = {
    "jlens": ["jlens", "ai_proposal", "jman_sales"],
    "marketplace": ["jlens", "ai_proposal", "jman_sales", "marketplace"],
    "nexus": ["jlens", "ai_proposal", "jman_sales", "nexus"],
    "jqa": ["jlens", "ai_proposal", "jman_sales", "jqa"],
}

DEFAULT_MODELS = ["gpt-4.1-mini", "gpt-5-chat", "DeepSeek-R1", "llama-3.3-70b-instruct"]

DOMAIN_TO_CLIENT = {
    "jlens.jmangroup.com": "jlens",
    "marketplace.jmangroup.com": "marketplace",
    "nexus.jmangroup.com": "nexus",
    "jqa.jmangroup.com": "jqa",
}
