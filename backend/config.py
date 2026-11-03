"""Settings for the agent team: paths, the one model, the MCP connection, and the limits.

Model    gpt-6-luna for every agent, through Portkey. The key is the same PORTKEY_API_KEY
         used in Homework 3 and 4: read from the environment (it is set as a Windows user
         variable), or from a .env file in the project folder or backend/ (see .env.example).
MCP      every shop fact comes from the campus-customs MCP server, started the same way
         .mcp.json starts it for the vibe coder. There is no other way to the database.
Limits   one shared budget per task, so a chain of agents cannot run away (see harness.md).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from mcp.client.stdio import get_default_environment
from openai import AsyncOpenAI
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
SHOP_RULES_PATH = PROMPTS_DIR / "shop_rules.md"
ORIGINAL_DB_PATH = ROOT / "data" / "campus_customs.db"  # as delivered; only ever read
# What the MCP server works on. CAMPUS_CUSTOMS_DB and CAMPUS_CUSTOMS_AUDIT point a test run at
# scratch files instead, so testing never touches the real working copy or audit trail.
WORKING_DB_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DB") or ROOT / "data" / "campus_customs_new.db")
AUDIT_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_AUDIT") or ROOT / "output" / "audit_trail.json")
MCP_CONFIG_PATH = ROOT / ".mcp.json"
MCP_SERVER_NAME = "campus-customs"

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL_NAME = "gpt-6-luna"  # the only model any agent uses; deliberately not configurable

# --- Limits that keep token use in check ------------------------------------------------
# One budget for the whole task: every agent a task reaches adds to the same usage, so
# these caps cover the Boss and all the specialists together.
TEAM_LIMITS = UsageLimits(request_limit=50, tool_calls_limit=80, total_tokens_limit=400_000)
MODEL_SETTINGS = OpenAIResponsesModelSettings(
    max_tokens=3_000,  # per model response
    openai_reasoning_effort="low",  # enough to plan, without paying for long hidden reasoning
)
MAX_DELEGATION_DEPTH = 3  # e.g. Boss -> Accounting -> Facilities, and no further
MAX_DELEGATIONS = 10  # ask_<agent> calls per task, across all agents
MAX_TASK_CHARS = 2_000  # longest task text one agent may hand another
RETRIES = 2  # times a tool error or a bad report can send an agent back to try again

# Tools on the MCP server that no agent may ever have (a person approves and pays or buys).
HUMAN_ONLY_TOOLS = frozenset({"record_payment", "record_purchase"})


class MissingAPIKeyError(RuntimeError):
    pass


def make_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey's Responses API (its chat endpoint can't mix tools and reasoning)."""
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise MissingAPIKeyError("Missing PORTKEY_API_KEY. Set it, or copy .env.example to .env and add it there.")
    client = AsyncOpenAI(base_url=PORTKEY_BASE_URL, api_key=api_key)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def _mcp_command(command: str, args: list[str]) -> tuple[str, list[str]]:
    """The .mcp.json command, made to work on any machine.

    "python" (or a Python path that doesn't exist here) means this same interpreter, so the
    server runs in the backend's environment; relative paths are taken from the project root.
    """
    path = Path(command) if Path(command).is_absolute() else ROOT / command
    if command in ("python", "python3", "py") or not path.exists():
        command = sys.executable  # run the server in this same environment
    else:
        command = str(path)
    args = [str(ROOT / a) if (ROOT / a).exists() else a for a in args]
    return command, args


def shop_client(dry_run: bool = False, desk: bool = False) -> Client:
    """A client for the campus-customs MCP server, launched the way .mcp.json says.

    The server gets a minimal environment (not the Portkey key). dry_run starts it
    read-only, so write tools report what they would do and change nothing. desk=True is
    only for the backend's own connection, which serves the people at the dashboard: it is
    the one connection where the server will record a payment or purchase or reset the
    database. The agents' connections never get it.
    """
    server = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))["mcpServers"][MCP_SERVER_NAME]
    env = {**get_default_environment(), **server.get("env", {}), "CAMPUS_CUSTOMS_DB": str(WORKING_DB_PATH)}
    env.pop("CAMPUS_CUSTOMS_DESK", None)
    if desk:
        env["CAMPUS_CUSTOMS_DESK"] = "1"
    if dry_run:
        env["CAMPUS_CUSTOMS_READ_ONLY"] = "1"
    command, args = _mcp_command(server["command"], server.get("args", []))
    transport = StdioTransport(command=command, args=args, env=env, cwd=str(ROOT))
    return Client(transport)


def shop_toolset(dry_run: bool = False) -> MCPToolset:
    """The MCP server as a PydanticAI toolset, for the agents."""
    return MCPToolset(shop_client(dry_run), id=MCP_SERVER_NAME, max_retries=RETRIES)
