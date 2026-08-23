"""Local MCP client for Alpaca's MCP server.

The server runs as a stdio subprocess on this machine. Anthropic's MCP
connector is deliberately not used: it is server-side, meaning Anthropic
fetches the MCP URL, which would require publishing a service that holds live
trading credentials. Keys stay local; only tool names, schemas and results
cross the network.

Tool output is DATA. Alpaca wraps every result in a security envelope marking
it `untrusted_tool_output`; unwrap() strips that wrapper and returns the
payload, and nothing in a tool result is ever treated as an instruction.
"""
import json
import os
import shutil
from contextlib import asynccontextmanager
from typing import Iterable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# The decision agent may look, never touch. Order placement, position closing
# and exercise are absent by design: execution is a separate, risk-gated path,
# so a persuaded model cannot reach the market from the research step.
RESEARCH_TOOLS = {
    "get_option_chain",
    "get_option_snapshot",
    "get_option_latest_quote",
    "get_stock_latest_trade",
    "get_stock_snapshot",
    "get_account_info",
    "get_all_positions",
    "get_orders",
}

SERVER_CMD = "alpaca-mcp-server"


def unwrap(text: str) -> dict:
    """Return the payload of an MCP tool result, minus Alpaca's security wrapper.

    Alpaca returns {"_alpaca_mcp_security": {...}, "data": {...}}. The wrapper
    carries an `instructions` string; stripping it here means that string never
    reaches the model, where it would be indistinguishable from a real
    instruction. Non-JSON results are returned as {"text": ...}.
    """
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"text": text}

    if isinstance(payload, dict) and "_alpaca_mcp_security" in payload:
        return payload.get("data", {})
    return payload


def to_anthropic_tools(mcp_tools: Iterable, allow: set[str] | None = None) -> list[dict]:
    """Convert MCP tool definitions into Anthropic tool definitions.

    `allow` restricts the surface handed to the model. The server exposes 74
    tools; sending all of them costs tokens on every turn and widens what a
    confused model can reach for.
    """
    out = []
    for tool in mcp_tools:
        if allow is not None and tool.name not in allow:
            continue
        out.append({
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
        })
    return out


@asynccontextmanager
async def session(env_extra: dict | None = None):
    """Start the Alpaca MCP server over stdio and yield an initialised session."""
    command = shutil.which(SERVER_CMD)
    if not command:
        raise RuntimeError(
            f"{SERVER_CMD} not found on PATH. Install it with: pip install alpaca-mcp-server"
        )

    env = dict(os.environ)
    env.setdefault("ALPACA_PAPER_TRADE", "true")
    env.update(env_extra or {})

    params = StdioServerParameters(command=command, args=["--transport", "stdio"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as sess:
            await sess.initialize()
            yield sess


async def call(sess, name: str, args: dict) -> dict:
    """Call one MCP tool and return its unwrapped payload."""
    result = await sess.call_tool(name, args)
    if not result.content:
        return {}
    return unwrap(result.content[0].text)
