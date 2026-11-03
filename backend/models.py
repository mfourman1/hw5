"""Data types for the Campus Customs agent team.

RoleName      the five agents
AgentSpec     what defines one agent: its prompt file, MCP tools, and what it handles
TeamDeps      what every agent run knows: the task, who asked it, and shared limits
AgentReport   the structured answer every agent returns (output_type of every agent)
TaskResult    what one top-level task returns: the report plus how the run ended
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

RoleName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
ROLES: tuple[RoleName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

StopReason = Literal["final_answer", "usage_limit", "error"]


@dataclass(frozen=True)
class AgentSpec:
    role: RoleName
    title: str  # how other agents and people refer to it ("Customer Service")
    prompt_file: str  # file in backend/prompts/
    handles: str  # one line on what to ask this agent for (used in its ask_<role> tool)
    mcp_tools: tuple[str, ...]  # the only MCP server tools this agent can call


@dataclass
class TeamState:
    """Shared by every agent run inside one top-level task."""

    dry_run: bool = False
    delegations: int = 0


@dataclass
class TeamDeps:
    task_id: str  # one id for the whole task, across every agent it reaches
    run_id: str  # this agent's run
    role: RoleName
    chain: tuple[RoleName, ...]  # who asked whom, from the first agent down to this one
    parent_run_id: str | None = None
    state: TeamState = field(default_factory=TeamState)


# --- What agents return --------------------------------------------------------------------


class Fact(BaseModel):
    detail: str = Field(description="One fact with its numbers, e.g. 'CC-TEE-WHITE size S: 0 on hand (Aisle B)'.")
    source: str = Field(description="Where it came from: the MCP tool (e.g. 'check_stock') or the agent that reported it.")


class ApprovalRequest(BaseModel):
    action: str = Field(description="What a person must approve, e.g. 'Pay invoice 501 to Bulldog Print Co'.")
    amount: float | None = Field(default=None, description="Dollars involved, if any.")
    ticket_id: int | None = None
    reason: str = Field(description="Why it needs a person and what the agent recommends.")


class AgentReport(BaseModel):
    """Every agent's answer, to the agent that asked it or to the human manager."""

    agent: RoleName
    ticket_ids: list[int] = Field(default_factory=list, description="Tickets this report covers.")
    status: Literal["done", "needs_approval", "blocked", "needs_info"] = Field(
        description="done = your part is finished; needs_approval = a person must approve something; "
        "blocked = a rule or missing stock/cash stops it; needs_info = facts are missing."
    )
    summary: str = Field(description="Two to five sentences: what you found, what you decided, and why.")
    facts: list[Fact] = Field(default_factory=list, description="The facts your answer rests on, each with its source.")
    actions_taken: list[str] = Field(
        default_factory=list, description="Changes made in this task: ticket notes, status changes, payment proposals."
    )
    approvals_needed: list[ApprovalRequest] = Field(default_factory=list)
    customer_message: str | None = Field(
        default=None,
        description="Customer Service only (the Boss may pass one on unchanged): a draft for a person to send. "
        "Never sent automatically.",
    )
    next_steps: list[str] = Field(default_factory=list, description="Who should do what next.")


class Usage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0


class TaskResult(BaseModel):
    task_id: str
    agent: RoleName  # the agent the task was given to
    task: str
    dry_run: bool
    stop_reason: StopReason
    report: AgentReport | None = None
    error: str | None = None
    delegations: int = 0
    usage: Usage = Field(default_factory=Usage)
    duration_ms: int = 0
