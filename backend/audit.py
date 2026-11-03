"""Append-only audit trail of every agent-loop step: output/audit_trail.json.

The file is one JSON array that only grows. Each record is written over the closing "]"
and the "]" is put back after it, so earlier records are never rewritten and nothing
clears the file between runs.

Every record has: time (UTC), task_id (one per top-level task), run_id and parent_run_id
(which agent run, and which run asked it), agent, chain (who asked whom), depth, step
(order inside that run), event, dry_run, and team_usage (requests and tokens used so far
by the whole task). Events:

    task_start      a person gave a task to an agent
    agent_start     an agent run began: the task text it was given
    model_request   what went to the model this step: tool results and retry messages
    model_response  what the model sent back: tool calls with their arguments, any text,
                    tokens for this response, finish reason
    agent_end       the agent's report: status, summary, approvals it asks for
    agent_error     the run failed (the error is recorded)
    delegation_refused  an ask_<agent> call was stopped by a loop or limit guard
    task_end        how the task ended (final_answer, usage_limit, error), total usage
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import RunUsage

from config import AUDIT_PATH
from models import TeamDeps

SHORT = 400  # characters kept from any one tool result, argument or text
_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def short(value: Any, limit: int = SHORT) -> Any:
    """Numbers stay numbers and small lists/dicts stay as they are; anything long is cut to `limit` characters."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return value if isinstance(value, (str, list, dict)) else text
    return text[: limit - 1] + "…"


def append(record: dict[str, Any], path: Path | None = None) -> None:
    """Add one record to the end of the JSON array without rewriting earlier records."""
    path = path or AUDIT_PATH
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            path.write_text(f"[\n{line}\n]\n", encoding="utf-8")
            return
        with open(path, "r+b") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            back = min(size, 4096)
            f.seek(size - back)
            tail = f.read(back)
            end = tail.rfind(b"]")
            if end == -1:
                raise ValueError(f"{path} is not a JSON array; not appending to it")
            empty = tail[:end].rstrip().endswith(b"[")
            f.seek(size - back + end)
            f.write((b"\n" if empty else b",\n") + line.encode("utf-8") + b"\n]\n")
            f.truncate()


def usage_summary(usage: RunUsage | None) -> dict[str, int]:
    if usage is None:
        return {}
    return {
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
    }


def event(deps: TeamDeps | None, event_name: str, step: int | None = None,
          usage: RunUsage | None = None, **details: Any) -> None:
    record: dict[str, Any] = {"time": now(), "event": event_name}
    if deps is not None:
        record.update(
            task_id=deps.task_id,
            run_id=deps.run_id,
            parent_run_id=deps.parent_run_id,
            agent=deps.role,
            chain=list(deps.chain),
            depth=len(deps.chain) - 1,
            dry_run=deps.state.dry_run,
        )
    if step is not None:
        record["step"] = step
    record.update(details)
    if usage is not None:
        record["team_usage"] = usage_summary(usage)
    append(record)


def request_details(request: ModelRequest) -> dict[str, Any]:
    """Tool results and retry messages going to the model (the agent's own instructions are left out)."""
    results, retries, prompts = [], [], []
    for part in request.parts:
        if isinstance(part, ToolReturnPart):
            results.append({"tool": part.tool_name, "call_id": part.tool_call_id, "result": short(part.content, 800)})
        elif isinstance(part, RetryPromptPart):
            retries.append({"tool": part.tool_name, "message": short(part.content)})
        elif isinstance(part, UserPromptPart):
            prompts.append(short(part.content))
    details: dict[str, Any] = {"tool_results": results}
    if retries:
        details["retries"] = retries
    if prompts:
        details["user_prompt"] = prompts
    return details


def response_details(response: ModelResponse) -> dict[str, Any]:
    """Tool calls (with arguments), text, and tokens from one model response."""
    calls, texts, thinking = [], [], 0
    for part in response.parts:
        if isinstance(part, ToolCallPart):
            calls.append({"tool": part.tool_name, "call_id": part.tool_call_id,
                          "args": {k: short(v) for k, v in part.args_as_dict().items()}})
        elif isinstance(part, TextPart) and part.content.strip():
            texts.append(short(part.content))
        elif isinstance(part, ThinkingPart):
            thinking += 1
    usage = response.usage
    details: dict[str, Any] = {
        "model": response.model_name,
        "tool_calls": calls,
        "tokens": {"input": usage.input_tokens, "output": usage.output_tokens},
        "finish_reason": response.finish_reason,
    }
    if texts:
        details["text"] = texts
    if thinking:
        details["thinking_parts"] = thinking
    return details
