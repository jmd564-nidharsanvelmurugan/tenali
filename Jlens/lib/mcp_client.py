import asyncio
from typing import List, Any
import tempfile
import os
from hashlib import md5
from mcp.types import TextContent, ImageContent
from contextlib import AsyncExitStack, AbstractAsyncContextManager
from dataclasses import dataclass
import json
import logging
import asyncssh
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from db.models import McpDbConfig, McpDbType

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------
@dataclass
class SessionInfo:
    session: ClientSession
    exit_stack: AbstractAsyncContextManager
    last_used: float


# ------------------------------------------------------------------
# In-memory caches
# ------------------------------------------------------------------
SESSIONS: dict[str, SessionInfo | ClientSession] = {}
TOOL_LIST: dict[str, List[dict]] = {}
RESOURCE_LIST: dict[str, List[dict]] = {}
SSH_TUNNELS: dict[str, asyncssh.SSHClientConnection] = {}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _make_key(mcp_config: McpDbConfig) -> str:
    raw = f"{mcp_config.type}:{mcp_config.db_uri}:{mcp_config.read_only}:{mcp_config.ssh_tunnel}"
    return md5(raw.encode()).hexdigest()


def _get_session(session_info: SessionInfo | ClientSession) -> ClientSession:
    return session_info if isinstance(session_info, ClientSession) else session_info.session


def _json_error(msg: str) -> str:
    return json.dumps([{"type": "text", "text": msg}])


# ------------------------------------------------------------------
# SSH tunnel
# ------------------------------------------------------------------
async def _open_ssh_tunnel(mcp_config: McpDbConfig) -> int:
    key = _make_key(mcp_config)

    # Reuse tunnel if already opened
    if key in SSH_TUNNELS:
        return mcp_config.ssh_local_port

    ssh_kwargs = {}
    tmpfile = None

    try:
        if pwd := mcp_config.get_ssh_password():
            ssh_kwargs["password"] = pwd

        if pkey := mcp_config.get_ssh_private_key():
            pem = pkey.replace("\\n", "\n")
            tmpfile = tempfile.NamedTemporaryFile(mode="w", delete=False)
            tmpfile.write(pem)
            tmpfile.close()
            os.chmod(tmpfile.name, 0o600)
            ssh_kwargs["client_keys"] = [tmpfile.name]

        conn = await asyncssh.connect(
            host=mcp_config.ssh_host,
            port=mcp_config.ssh_port or 22,
            username=mcp_config.ssh_username,
            known_hosts=None,
            **ssh_kwargs,
        )

        await conn.forward_local_port(
            "127.0.0.1",
            mcp_config.ssh_local_port,
            mcp_config.ssh_remote_host,
            mcp_config.ssh_remote_port,
        )

        SSH_TUNNELS[key] = conn
        return mcp_config.ssh_local_port

    except Exception as e:
        logger.error("SSH tunnel setup failed: %s", str(e))
        raise RuntimeError(f"Failed to open SSH tunnel: {e}") from e

    finally:
        if tmpfile and os.path.exists(tmpfile.name):
            try:
                os.unlink(tmpfile.name)
            except Exception:
                pass


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------
async def fetch_tools_from_mcp(mcp_config: McpDbConfig) -> List[dict]:
    key = _make_key(mcp_config)

    if key in TOOL_LIST:
        return TOOL_LIST[key]

    if key in SESSIONS:
        session = _get_session(SESSIONS[key])
        TOOL_LIST[key] = await session.list_tools()
        return TOOL_LIST[key]

    db_uri = mcp_config.db_uri
    if mcp_config.ssh_tunnel:
        await _open_ssh_tunnel(mcp_config)

    if mcp_config.type != McpDbType.postgres:
        raise ValueError(f"Unsupported MCP type: {mcp_config.type}")

    # SSL-based MCP
    if "sslmode" in db_uri:
        server_params = StdioServerParameters(
            command="postgres-mcp",
            args=["--access-mode=unrestricted"],
            env={"DATABASE_URI": db_uri},
        )
    else:
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-postgres", db_uri],
        )

    exit_stack = AsyncExitStack()
    try:
        read, write = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await session.initialize()

        SESSIONS[key] = SessionInfo(
            session=session,
            exit_stack=exit_stack,
            last_used=time.time(),
        )

        TOOL_LIST[key] = await session.list_tools()
        return TOOL_LIST[key]

    except Exception as e:
        await exit_stack.aclose()
        logger.error("Failed to initialize MCP session: %s", str(e))
        raise RuntimeError(f"Failed to connect to MCP: {e}") from e


async def call_tool(
    mcp_config: McpDbConfig, tool_name: str, args: dict[str, Any]
) -> str:
    key = _make_key(mcp_config)

    try:
        tools = await fetch_tools_from_mcp(mcp_config)
        tool_names = {t.name for t in tools.tools}

        if tool_name not in tool_names:
            return _json_error(
                f"Tool '{tool_name}' not found. Available: {sorted(tool_names)}"
            )

        session = _get_session(SESSIONS[key])
        response = await session.call_tool(tool_name, args)

        result = []
        for item in response.content:
            if isinstance(item, TextContent):
                result.append({"type": "text", "text": item.text})
            elif isinstance(item, ImageContent):
                result.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{item.mimeType};base64,{item.data}"
                        },
                    }
                )

        return json.dumps(result)

    except Exception as e:
        logger.exception("Error while calling MCP tool %s", tool_name)
        return _json_error(f"Error: {str(e)}")


# ------------------------------------------------------------------
# Resources
# ------------------------------------------------------------------
async def fetch_resources_from_mcp(mcp_config: McpDbConfig) -> List[dict]:
    key = _make_key(mcp_config)

    if key in RESOURCE_LIST:
        return RESOURCE_LIST[key]

    if key not in SESSIONS:
        await fetch_tools_from_mcp(mcp_config)

    session = _get_session(SESSIONS[key])
    resources = await session.list_resources()
    RESOURCE_LIST[key] = resources
    return resources


async def get_resource(mcp_config: McpDbConfig, resource_name: str) -> str:
    key = _make_key(mcp_config)

    try:
        resources = await fetch_resources_from_mcp(mcp_config)
        names = {r.name for r in resources.resources}

        if resource_name not in names:
            return _json_error(
                f"Resource '{resource_name}' not found. Available: {sorted(names)}"
            )

        session = _get_session(SESSIONS[key])
        resource = await session.read_resource(resource_name)

        result = []
        for item in resource.content:
            if isinstance(item, TextContent):
                result.append({"type": "text", "text": item.text})
            elif isinstance(item, ImageContent):
                result.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{item.mimeType};base64,{item.data}"
                        },
                    }
                )

        return json.dumps(result)

    except Exception as e:
        logger.exception("Error while reading MCP resource %s", resource_name)
        return _json_error(f"Error: {str(e)}")


# ------------------------------------------------------------------
# Shutdown
# ------------------------------------------------------------------
async def shutdown_all() -> None:
    errors = []

    for key, session_info in list(SESSIONS.items()):
        try:
            if hasattr(session_info, "exit_stack"):
                await session_info.exit_stack.aclose()
        except Exception as e:
            errors.append((key, str(e)))
            logger.error("Failed to close session %s: %s", key, str(e))

    for key, conn in list(SSH_TUNNELS.items()):
        try:
            conn.close()
            await conn.wait_closed()
        except Exception as e:
            errors.append((key, f"SSH close failed: {e}"))
            logger.error("Failed to close SSH tunnel %s: %s", key, str(e))

    SESSIONS.clear()
    TOOL_LIST.clear()
    RESOURCE_LIST.clear()
    SSH_TUNNELS.clear()

    if errors:
        raise RuntimeError(f"Some sessions failed to close: {errors}")
