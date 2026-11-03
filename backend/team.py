"""The Campus Customs agent team: five PydanticAI agents that share the MCP server and
can hand work to each other.

How it fits together
    agents/       one SPEC per agent: its prompt file, the MCP tools it may call, and what
                  teammates should ask it for
    prompts/      shop_rules.md (given to every agent) plus one prompt per agent
    models.py     AgentReport (every agent's output), TeamDeps, TaskResult
    MCP           one campus-customs server per task (config.shop_toolset). Each agent sees
                  only its own tools; record_payment is never given to any agent.
    delegation    every agent has an ask_<role> tool for each of the other four (full
                  connectivity). The asked agent runs its own loop on the same shared
                  usage and returns its AgentReport as the tool result. Guards: an agent
                  already in the chain can't be asked again (no loops), chains stop at
                  MAX_DELEGATION_DEPTH, and a task gets MAX_DELEGATIONS hand-offs in all.
    agent loop    each run is stepped node by node with Agent.iter, and every step is
                  appended to output/audit_trail.json (audit.py)
    limits        TEAM_LIMITS (model requests, tool calls, tokens) cover the whole task
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic_ai import Agent, CallToolsNode, ModelRequestNode, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage

import audit
from agents import SPECS
from config import (
    HUMAN_ONLY_TOOLS,
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS,
    MAX_TASK_CHARS,
    MODEL_NAME,
    MODEL_SETTINGS,
    PROMPTS_DIR,
    RETRIES,
    SHOP_RULES_PATH,
    TEAM_LIMITS,
    make_model,
    shop_toolset,
)
from models import (
    ROLES,
    AgentReport,
    AgentSpec,
    RoleName,
    StopReason,
    TaskResult,
    TeamDeps,
    TeamState,
    Usage,
)

# Only Customer Service writes to people outside the shop; the Boss may pass its draft on.
MAY_DRAFT_MESSAGES: frozenset[RoleName] = frozenset({"customer_service", "boss"})


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _titles(chain: tuple[RoleName, ...]) -> str:
    return " -> ".join(SPECS[r].title for r in chain)


def task_context(ctx: RunContext[TeamDeps]) -> str:
    """The 'This task' part of every agent's instructions, rebuilt before each model request."""
    deps = ctx.deps
    me = SPECS[deps.role]
    asked_by = "the human manager" if len(deps.chain) == 1 else f"the {SPECS[deps.chain[-2]].title} agent"
    lines = [
        "## This task",
        "",
        f"- You are the {me.title} agent (task {deps.task_id}). Set `agent` in your report to \"{deps.role}\".",
        f"- You were asked by {asked_by}. Chain so far: {_titles(deps.chain)}.",
    ]
    left = MAX_DELEGATIONS - deps.state.delegations
    can_ask = [SPECS[r].title for r in ROLES if r not in deps.chain]
    if len(deps.chain) < MAX_DELEGATION_DEPTH and left > 0:
        lines.append(f"- You may hand work to: {', '.join(can_ask)}. {left} hand-offs are left for the whole task.")
    else:
        lines.append("- You cannot hand work to anyone else from here. Finish with what you have and list gaps in next_steps.")
    if deps.state.dry_run:
        lines.append(
            "- DRY RUN: write tools only report what they would do and nothing is saved. "
            "Say \"(dry run, not saved)\" next to any such change in actions_taken."
        )
    return "\n".join(lines)


class Team:
    """Builds the five agents for one set of runs. dry_run starts the MCP server read-only."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.toolset = shop_toolset(dry_run)
        self.model = make_model()
        self.rules = SHOP_RULES_PATH.read_text(encoding="utf-8")
        self.agents: dict[RoleName, Agent[TeamDeps, AgentReport]] = {r: self._build(SPECS[r]) for r in ROLES}

    def _build(self, spec: AgentSpec) -> Agent[TeamDeps, AgentReport]:
        allowed = frozenset(spec.mcp_tools) - HUMAN_ONLY_TOOLS
        return Agent(
            self.model,
            name=spec.role,
            deps_type=TeamDeps,
            output_type=AgentReport,
            instructions=[self.rules, (PROMPTS_DIR / spec.prompt_file).read_text(encoding="utf-8"), task_context],
            toolsets=[self.toolset.filtered(lambda ctx, tool_def: tool_def.name in allowed)],
            tools=[self._ask_tool(SPECS[other]) for other in ROLES if other != spec.role],
            retries=RETRIES,
            model_settings=MODEL_SETTINGS,
        )

    # --- Delegation -----------------------------------------------------------------------

    def _ask_tool(self, target: AgentSpec) -> Tool[TeamDeps]:
        async def ask(ctx: RunContext[TeamDeps], task: str) -> dict[str, Any] | str:
            deps = ctx.deps
            refusal = self._refusal(deps, target.role, task)
            if refusal:
                audit.event(deps, "delegation_refused", usage=ctx.usage, to=target.role, reason=refusal)
                return refusal
            deps.state.delegations += 1
            child = TeamDeps(
                task_id=deps.task_id,
                run_id=new_id("run"),
                role=target.role,
                chain=(*deps.chain, target.role),
                parent_run_id=deps.run_id,
                state=deps.state,
            )
            try:
                report = await self.run_agent(child, task, ctx.usage)
            except UsageLimitExceeded:
                raise  # the whole task is over budget: stop every agent
            except Exception as err:  # noqa: BLE001 - the asking agent decides what to do without it
                return f"The {target.title} agent could not finish ({type(err).__name__}: {err}). Work with what you have."
            return report.model_dump(exclude_none=True)

        return Tool(
            ask,
            name=f"ask_{target.role}",
            description=(
                f"Hand one specific piece of work to the {target.title} agent and get its report back. "
                f"Ask it for: {target.handles}. Write `task` as a complete request: the ticket id, the exact "
                "question, the facts it needs (sku, size, qty, lease or invoice id), and what you want back."
            ),
        )

    @staticmethod
    def _refusal(deps: TeamDeps, target: RoleName, task: str) -> str | None:
        title = SPECS[target].title
        if target in deps.chain:
            return (f"The {title} agent is already working on this request ({_titles(deps.chain)}). "
                    "Don't ask it again: use what you have, or report needs_info.")
        if len(deps.chain) >= MAX_DELEGATION_DEPTH:
            return (f"Hand-off limit reached ({MAX_DELEGATION_DEPTH} agents deep). Finish your part with "
                    "what you have and list what is missing in next_steps.")
        if deps.state.delegations >= MAX_DELEGATIONS:
            return f"This task has used all {MAX_DELEGATIONS} hand-offs. Finish with what you have."
        if not task.strip():
            return "The request is empty. Say exactly what you need."
        if len(task) > MAX_TASK_CHARS:
            return f"Keep the request under {MAX_TASK_CHARS} characters."
        return None

    # --- The agent loop -------------------------------------------------------------------

    async def run_agent(self, deps: TeamDeps, task: str, usage: RunUsage) -> AgentReport:
        """Run one agent to its report, recording every loop step in the audit trail."""
        agent = self.agents[deps.role]
        audit.event(deps, "agent_start", step=0, usage=usage, task=audit.short(task, MAX_TASK_CHARS))
        step = 0
        try:
            async with agent.iter(task, deps=deps, usage=usage, usage_limits=TEAM_LIMITS) as run:
                # The loop alternates: a request goes to the model, the model answers (tool calls
                # or the final report), the tools run, and their results go in the next request.
                async for node in run:
                    if isinstance(node, ModelRequestNode):
                        step += 1
                        audit.event(deps, "model_request", step, usage, **audit.request_details(node.request))
                    elif isinstance(node, CallToolsNode):
                        step += 1
                        audit.event(deps, "model_response", step, usage, **audit.response_details(node.model_response))
            report = run.result.output
        except Exception as err:
            audit.event(deps, "agent_error", step + 1, usage, error=audit.short(f"{type(err).__name__}: {err}"))
            raise

        updates: dict[str, Any] = {"agent": deps.role}
        if deps.role not in MAY_DRAFT_MESSAGES and report.customer_message:
            updates["customer_message"] = None  # only Customer Service drafts outside messages
        report = report.model_copy(update=updates)
        audit.event(
            deps,
            "agent_end",
            step + 1,
            usage,
            status=report.status,
            ticket_ids=report.ticket_ids,
            summary=audit.short(report.summary, 800),
            actions_taken=[audit.short(a) for a in report.actions_taken],
            approvals_needed=[a.model_dump() for a in report.approvals_needed],
            customer_message=audit.short(report.customer_message, 2000) if report.customer_message else None,
        )
        return report

    async def run_task(
        self,
        task: str,
        role: RoleName = "boss",
        *,
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> TaskResult:
        """Give one task to one agent (the Boss by default) and run it, and every hand-off, to the end.

        meta (for example the ticket id and who started the run) is saved on the task's
        task_start and task_end audit records.
        """
        meta = meta or {}
        state = TeamState(dry_run=self.dry_run)
        deps = TeamDeps(
            task_id=task_id or new_id("task"), run_id=new_id("run"), role=role, chain=(role,), state=state
        )
        usage = RunUsage()
        started = time.perf_counter()
        audit.event(
            deps,
            "task_start",
            **meta,
            task=audit.short(task, MAX_TASK_CHARS),
            model=MODEL_NAME,
            limits={
                "request_limit": TEAM_LIMITS.request_limit,
                "tool_calls_limit": TEAM_LIMITS.tool_calls_limit,
                "total_tokens_limit": TEAM_LIMITS.total_tokens_limit,
                "max_tokens_per_response": MODEL_SETTINGS.get("max_tokens"),
                "max_delegation_depth": MAX_DELEGATION_DEPTH,
                "max_delegations": MAX_DELEGATIONS,
            },
        )
        report: AgentReport | None = None
        stop: StopReason = "final_answer"
        error: str | None = None
        try:
            async with self.toolset:  # one MCP server process for the whole task
                report = await self.run_agent(deps, task, usage)
        except UsageLimitExceeded as err:
            stop, error = "usage_limit", str(err)
        except Exception as err:  # noqa: BLE001 - recorded and returned, never hidden
            stop, error = "error", f"{type(err).__name__}: {err}"

        totals = audit.usage_summary(usage)
        result = TaskResult(
            task_id=deps.task_id,
            agent=role,
            task=task,
            dry_run=self.dry_run,
            stop_reason=stop,
            report=report,
            error=error,
            delegations=state.delegations,
            usage=Usage(**totals),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        audit.event(
            deps,
            "task_end",
            usage=usage,
            **meta,
            stop_reason=stop,
            error=audit.short(error) if error else None,
            report_status=report.status if report else None,
            delegations=state.delegations,
            duration_ms=result.duration_ms,
        )
        return result
