import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.language_models import BaseChatModel

load_dotenv()

def get_llm(temperature: float = 0) -> BaseChatModel:
    """Get LLM instance based on configuration."""
    use_azure = os.getenv("USE_AZURE", "true").lower() == "true"
    
    if use_azure:
        return AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            azure_deployment=os.getenv("AZURE_DEPLOYMENT"),
            api_version="2024-02-15-preview",
            temperature=0,
        )
    else:
        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY")
        )