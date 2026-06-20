import json
from typing import List
from mcp import ClientSession
from mcp.types import TextContent, ImageContent

from db.models import McpDbConfig
from .mcp_client import fetch_tools_from_mcp, call_tool
import os
import re
# from aiohttp import ClientSession
import httpx
from openai import AzureOpenAI, AsyncAzureOpenAI
import traceback
from dotenv import load_dotenv
from pprint import pprint


load_dotenv()

class ChatClient:
    def __init__(self, model_name: str = None) -> None:
        self.httpx_client = httpx.AsyncClient(
            base_url=os.environ["AZURE_OPENAI_ENDPOINT"],
            headers={"api-key": os.environ["AZURE_OPENAI_KEY"]},
            timeout=60.0,
        )
        # Use provided model or fallback to default
        self.deployment_name = model_name or os.environ.get("AZURE_OPENAI_DEPLOYMENT_MODEL_1", "gpt-4.1-mini")
        
        self.client = AsyncAzureOpenAI(
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_key=os.environ["AZURE_OPENAI_KEY"],
                api_version="2024-05-01-preview",
                http_client=self.httpx_client
            )
        self.messages = []
        self.mcp_config = []
        self.tools = dict()
        self.active_streams = []  # Track active response streams

        
    async def _cleanup_streams(self):
        """Helper method to clean up all active streams"""
        for stream in self.active_streams:
            try:
                await stream.aclose()
            except Exception:
                pass
        self.active_streams = []


    async def load_mcp_tools(self, mcp_configs: List[McpDbConfig]) -> List[dict]:
        """Load tools from multiple MCP configurations."""
        self.mcp_config.append(mcp_configs)
        for config in mcp_configs:
            tool = await fetch_tools_from_mcp(config)
            self.tools[config.name] = [
                {"name": t.name, "description": t.description, "parameters": t.inputSchema} for t in tool.tools
            ]

    async def get_active_tools(self) -> List[dict]:
        """Get active tools from the loaded MCP tools."""
        tools = []
        for tool in self.tools.values():
            tools.extend(list(tool))
        return [{"type": "function", "function": tool} for tool in tools]
    
    async def _call_mcp_tool(self, tool_name: str, args: dict) -> str:
        """Call a tool by name with arguments."""
        for connection_name, session_tools in self.tools.items():
            if any(tool.get("name") == tool_name for tool in session_tools):
                mcp_config = next((cfg for cfg in self.mcp_config[0] if cfg.name == connection_name), None)
                if mcp_config:
                    response = await call_tool(mcp_config, tool_name, args)
                    return response
        raise ValueError(f"Tool {tool_name} not found in any MCP configuration.")

    
    async def process_response_stream(self, response_stream, tools, temperature=0):
        """
        Process response stream to handle function calls without recursion.
        """
        function_arguments = ""
        function_name = ""
        tool_call_id = ""
        is_collecting_function_args = False
        collected_messages = []
        tool_called = False
        
        # Add to active streams for cleanup if needed
        self.active_streams.append(response_stream)
        
        try:
            async for part in response_stream:
                if part.choices == []:
                    continue
                delta = part.choices[0].delta
                finish_reason = part.choices[0].finish_reason
                
                # Process assistant content
                if delta.content:
                    collected_messages.append(delta.content)
                    yield delta.content
                
                # Handle tool calls
                if delta.tool_calls:
                    if len(delta.tool_calls) > 0:
                        tool_call = delta.tool_calls[0]
                        
                        # Get function name
                        if tool_call.function.name:
                            function_name = tool_call.function.name
                            tool_call_id = tool_call.id
                        
                        # Process function arguments delta
                        if tool_call.function.arguments:
                            function_arguments += tool_call.function.arguments
                            is_collecting_function_args = True
                
                # Check if we've reached the end of a tool call
                if finish_reason == "tool_calls" and is_collecting_function_args:
                    # Process the current tool call
                    mcp_name = None

                    # Add the assistant message with tool call
                    self.messages.append({
                        "role": "assistant", 
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "function": {
                                    "name": function_name,
                                    "arguments": function_arguments
                                },
                                "type": "function"
                            }
                        ]
                    })
                    
                    # Safely close the current stream before starting a new one
                    if response_stream in self.active_streams:
                        self.active_streams.remove(response_stream)
                        await response_stream.close()

                    # Attempt to parse function arguments safely
                    try:
                        # Detect if multiple JSON objects are present
                        if function_arguments.strip().count("{") > 1 and function_arguments.strip().count("}") > 1:
                            raise json.JSONDecodeError("Multiple JSON objects detected", function_arguments, 0)

                        function_args = json.loads(function_arguments)

                    except json.JSONDecodeError:
                        # Append a warning message to conversation
                        warning_msg = (
                            "⚠️ Multiple JSON objects detected in one tool call. "
                            "Only a single SQL statement per tool call is supported. "
                            "Please split your queries into separate calls."
                        )
                        self.messages.append({"role": "tool", 
                                              "content": warning_msg,
                                              "name": function_name,
                                              "tool_call_id": tool_call_id})

                        # Skip tool execution
                        self.last_tool_called = function_name
                        tool_called = True
                        break  # Exit the loop
                    else:
                        # Call the tool and add response to messages
                        func_response = await self._call_mcp_tool(function_name, function_args)
                        try:
                            parsed_response = json.loads(func_response)
                        except json.JSONDecodeError:
                            parsed_response = {"error": "Invalid JSON response from tool."}

                        self.messages.append({
                            "tool_call_id": tool_call_id,
                            "role": "tool",
                            "name": function_name,
                            "content": func_response if isinstance(parsed_response, str) else json.dumps(parsed_response),
                        })

                        # Set flag that tool was called and store the function name
                        self.last_tool_called = function_name
                        tool_called = True
                        break  # Exit the loop
                # Check if we've reached the end of assistant's response
                if finish_reason == "stop":
                    # Add final assistant message if there's content
                    if collected_messages:
                        final_content = ''.join([msg for msg in collected_messages if msg is not None])
                        if final_content.strip():
                            self.messages.append({"role": "assistant", "content": final_content})
                    
                    # Remove from active streams after normal completion
                    if response_stream in self.active_streams:
                        self.active_streams.remove(response_stream)
                    break  # Exit the loop instead of returning
                    
        except GeneratorExit:
            # Clean up this specific stream without recursive cleanup
            if response_stream in self.active_streams:
                self.active_streams.remove(response_stream)
                await response_stream.aclose()
            #raise
        except Exception as e:
            traceback.print_exc()
            if response_stream in self.active_streams:
                self.active_streams.remove(response_stream)
            self.last_error = str(e)
        
        # Store result in instance variables
        self.tool_called = tool_called
        self.last_function_name = function_name if tool_called else None
    
    @staticmethod
    def build_multimodal_message(content: str, image_urls: list[str]) -> dict:
        """Construct a user message with text and image_url content blocks."""
        blocks = [{"type": "text", "text": content}]
        for url in image_urls:
            blocks.append({"type": "image_url", "image_url": {"url": url}})
        return {"role": "user", "content": blocks}

    async def generate_response(self, temperature=0, image_urls: list[str] | None = None):
        
        # If images provided, convert the last user message to multimodal format
        if image_urls:
            for i in range(len(self.messages) - 1, -1, -1):
                if self.messages[i].get("role") == "user" and isinstance(self.messages[i].get("content"), str):
                    self.messages[i] = self.build_multimodal_message(self.messages[i]["content"], image_urls)
                    break

        # Handle multiple sequential function calls in a loop rather than recursively
        tools = await self.get_active_tools()
        while True:
            # Handle different parameter requirements for different models
            create_params = {
                "model": self.deployment_name,
                "messages": self.messages,
                "tools": tools,
                "stream": True,
                "temperature": temperature
            }
            
            # GPT-5.1 might need max_completion_tokens instead of max_tokens
            if "gpt-5.1" in self.deployment_name.lower():
                create_params["max_completion_tokens"] = 4000
            else:
                create_params["max_tokens"] = 4000
                
            response_stream = await self.client.chat.completions.create(**create_params)
            
            try:
                # Stream and process the response
                async for token in self._stream_and_process(response_stream, tools, temperature):
                    yield token
                
                # Check instance variables after streaming is complete
                if not self.tool_called:
                    break
                # Otherwise, loop continues for the next response that follows the tool call
            except GeneratorExit:
                # Ensure we clean up when the client disconnects
                await self._cleanup_streams()
                return

    async def _stream_and_process(self, response_stream, tools, temperature):
        """Helper method to yield tokens and return process result"""
        # Initialize instance variables before processing
        self.tool_called = False
        self.last_function_name = None
        self.last_error = None
        
        async for token in self.process_response_stream(response_stream, tools, temperature):
            yield token
        
        # Don't return values in an async generator - values are already stored in instance variables

def flatten(xss):
    return [x for xs in xss for x in xs]
