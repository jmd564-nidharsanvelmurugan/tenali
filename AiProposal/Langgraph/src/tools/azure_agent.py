# src/tools/azure_agent.py
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, AzureCliCredential, ChainedTokenCredential
from azure.ai.projects import AIProjectClient
from typing import Optional

load_dotenv()

# Azure AI Foundry Configuration
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT_PROPOSAL")
AZURE_API_KEY = os.getenv("AZURE_API_KEY_PROPOSAL")  # ✅ Your API Key
AGENT_NAME = os.getenv("AZURE_AGENT_PROPOSAL", "ai-proposal-langgraph-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "1")


class AzureAgentClient:
    """Client for interacting with Azure AI Agent using API Key."""
    
    def __init__(self):
        self._project_client = None
        self._openai_client = None
    
    def _get_credential(self):
        """
        Get Azure credentials using API Key.
        The API Key is passed directly to the client.
        """
        # ✅ For API Key, we don't need a credential object
        # We'll pass it directly to the client
        return None
    
    def _get_clients(self):
        """Get or initialize the Azure AI clients."""
        if self._project_client is None:
            # ✅ API Key authentication - pass api_key directly
            self._project_client = AIProjectClient(
                endpoint=AZURE_ENDPOINT,
                credential=DefaultAzureCredential(),  # Fallback for other auth
                api_key=AZURE_API_KEY,  # ✅ Your API Key
            )
            self._openai_client = self._project_client.get_openai_client()
        return self._openai_client
    
    def get_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Get response from Azure AI Agent using API Key.
        """
        try:
            client = self._get_clients()
            
            # Build messages
            input_messages = []
            if system_prompt:
                input_messages.append({"role": "user", "content": f"System instructions: {system_prompt}"})
            input_messages.append({"role": "user", "content": prompt})
            
            # ✅ Call the agent with API Key authentication
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
            
            return response.output_text
            
        except Exception as e:
            print(f"❌ Error calling Azure AI Agent: {e}")
            return f"Error: {str(e)}"


# Global instance
azure_agent = AzureAgentClient()


def get_agent_response(prompt: str, system_prompt: Optional[str] = None) -> str:
    """Convenience function to get response from Azure AI Agent."""
    return azure_agent.get_response(prompt, system_prompt)


# For testing
if __name__ == "__main__":
    print("=" * 60)
    print("Testing Azure AI Agent (with API Key)")
    print("=" * 60)
    
    print(f"Endpoint: {AZURE_ENDPOINT}")
    print(f"API Key: {'✅ Set' if AZURE_API_KEY else '✗ Not Set'}")
    print(f"Agent Name: {AGENT_NAME}")
    print(f"Agent Version: {AGENT_VERSION}")
    
    test_prompt = "Tell me what you can help with."
    try:
        response = get_agent_response(test_prompt)
        print(f"\n✅ Response: {response}")
        print("\n✅ Connection successful!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")