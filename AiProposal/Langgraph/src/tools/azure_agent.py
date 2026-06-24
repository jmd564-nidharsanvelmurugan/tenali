# src/tools/azure_agent.py
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from typing import Optional, Tuple, Dict
import re
import json

load_dotenv()

# Azure AI Foundry Configuration
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT_PROPOSAL")
AZURE_API_KEY = os.getenv("AZURE_API_KEY_PROPOSAL")
AGENT_NAME = os.getenv("AZURE_AGENT_PROPOSAL", "ai-proposal-langgraph-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "4")


class AzureAgentClient:
    """Client for interacting with Azure AI Agent using API Key."""
    
    def __init__(self):
        self._project_client = None
        self._openai_client = None
    
    def _get_clients(self):
        """Get or initialize the Azure AI clients."""
        if self._project_client is None:
            self._project_client = AIProjectClient(
                endpoint=AZURE_ENDPOINT,
                credential=DefaultAzureCredential(),
                api_key=AZURE_API_KEY,
            )
            self._openai_client = self._project_client.get_openai_client()
        return self._openai_client
    
    def clean_citations_preserve_flow(self, text):
        """
        Remove citations while preserving the natural flow of text
        """
        if not text:
            return text
            
        # Remove citation markers 【number:number†source】
        citation_pattern = r'【\d+:\d+†source】'
        text = re.sub(citation_pattern, '', text)
        
        # Remove any brackets that might be citations [1], [2], etc.
        text = re.sub(r'\[\d+\]', '', text)
        
        # Clean up punctuation
        text = re.sub(r'\.\s*\.', '.', text)
        text = re.sub(r'\.\s+,', ',', text)
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'\.\s+', '. ', text)
        
        return text
    
    def get_response(self, prompt: str, system_prompt: Optional[str] = None) -> Tuple[str, Dict[str, int]]:
        """
        Get response from Azure AI Agent using API Key.
        Returns: (cleaned_text, freq_blob_urls)
        """
        try:
            client = self._get_clients()
            
            # Build messages
            input_messages = []
            if system_prompt:
                input_messages.append({"role": "user", "content": f"System instructions: {system_prompt}"})
            input_messages.append({"role": "user", "content": prompt})
            
            # Call the agent
            response = client.responses.create(
                input=input_messages,
                extra_body={
                    "agent_reference": {
                        "name": AGENT_NAME,
                        "version": AGENT_VERSION,
                        "type": "agent_reference"
                    }
                },
            )
            
            # Parse KB documents and build frequency map
            freq_blob_urls = {}
            
            for item in response.output:
                if getattr(item, "name", "") == "knowledge_base_retrieve":
                    matches = re.findall(
                        r'【\d+:\d+†source】\s*(\{.*?\})',
                        item.output,
                        re.DOTALL
                    )
                    
                    for idx, doc in enumerate(matches, start=1):
                        try:
                            data = json.loads(doc)
                            blob_url = data.get("blob_url")
                            if blob_url:
                                freq_blob_urls[blob_url] = freq_blob_urls.get(blob_url, 0) + 1
                        except Exception:
                            pass
            
            # Clean citations from response
            cleaned_text = response.output_text
            
            return cleaned_text, freq_blob_urls
            
        except Exception as e:
            return f"Error: {str(e)}", {}


# Global instance
azure_agent = AzureAgentClient()


def get_agent_response(prompt: str, system_prompt: Optional[str] = None) -> Tuple[str, Dict[str, int]]:
    """Convenience function to get response from Azure AI Agent."""
    return azure_agent.get_response(prompt, system_prompt)