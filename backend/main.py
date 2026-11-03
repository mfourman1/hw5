"""Campus Customs backend: the FastAPI routes the dashboard calls.

Start it from the backend/ folder, with the project's environment active:

    ..\\.venv\\Scripts\\activate
    uvicorn main:app --reload --port 8000

Routes (also listed at http://localhost:8000/ and documented at /docs)
    GET  /api/tickets                     every ticket: open or resolved, where it stands on the desk,
                                          and its latest agent run (with what each agent did)
    POST /api/tickets/{ticket_id}/run     start the agent team (the Boss) on one ticket, in the background
    POST /api/tickets/{ticket_id}/resolve a person signs off a finished ticket that has no payment waiting
    POST /api/tickets/{ticket_id}/source  record where a ticket came from (online, in person, phone)
    GET  /api/runs/{task_id}              how one run is going, and the Boss's report when it ends
    GET  /api/events                      recent agent events: what each agent said and which tools it used
    GET  /api/payments/pending            payments and purchase orders the agents proposed that wait for a person
    POST /api/payments/approve            a person approves a proposed payment or purchase order: the only route that moves cash
    GET  /api/cash                        the current checking balance (cash_accounts)
    POST /api/reset                       put the working database back to the original values

When a ticket is resolved (the desk rule)
    - The team's run finishes with the Boss reporting "done" and no payment waiting: resolved
      straight away, in the Boss's name.
    - The run finishes with a payment or purchase order waiting: resolved as soon as a person
      approves the last one on that ticket, in that person's name.
    - The run finishes needing some other sign-off, or blocked: a person decides, with the
      resolve route.
    Practice (dry) runs never resolve anything.

Every shop fact and every change goes through the campus-customs MCP server, the same one the
agents use. The routes' connection is the desk (CAMPUS_CUSTOMS_DESK=1): the only one where the
server will record a payment or purchase, set a ticket's source, or reset the database.
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.client import Client
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

import audit
from config import AUDIT_PATH, MissingAPIKeyError, shop_client
from models import TaskResult
from team import Team, new_id

# What the Boss is asked to do when a person clicks "run" on a ticket.
TICKET_TASK = (
    "Work ticket {ticket_id} from start to finish. Read it, work out what it needs, and hand each "
    "question to the agent who owns it. Make sure the findings are noted on the ticket, that "
    "Accounting proposes any payment that is needed, and that Customer Service drafts a reply if "
    "the requester needs one. Then report the outcome and everything a person must approve."
)
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # the React dashboard (Vite)
CLOSED = ("resolved", "closed")
# A person approving or signing off can't use a name like these (same idea as record_payment).
AGENT_WORDS = {"boss", "inventory", "accounting", "facilities", "customer", "service",
               "agent", "assistant", "bot", "system", "llm", "gpt"}

DeskState = Literal["open", "running", "awaiting_approval", "needs_signoff", "needs_attention", "resolved"]


@dataclass
class Run:
    task_id: str
    ticket_id: int
    dry_run: bool
    started: str
    status: Literal["running", "finished", "failed"] = "running"
    result: TaskResult | None = None
    error: str | None = None
    resolved_by_run: bool = False
    job: asyncio.Task | None = field(default=None, repr=False)


RUNS: dict[str, Run] = {}
_shop: Client | None = None  # the routes' MCP connection (opened in lifespan)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One MCP server process for the routes, kept open while the backend runs. Each agent run
    # starts its own (see team.py), so a long run never blocks these routes.
    global _shop
    async with shop_client(desk=True) as client:  # the desk: the only connection that can pay
        _shop = client
        yield
        _shop = None
    for run in RUNS.values():
        if run.job and not run.job.done():
            run.job.cancel()


app = FastAPI(title="Campus Customs backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=DASHBOARD_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


async def mcp(tool: str, **args: Any) -> dict[str, Any]:
    """Call one campus-customs MCP tool and return its result."""
    if _shop is None:
        raise HTTPException(status_code=503, detail="The MCP server is not connected yet.")
    try:
        result = await _shop.call_tool(tool, args)
    except ToolError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return result.structured_content or {}


def _running(ticket_id: int | None = None) -> list[Run]:
    return [r for r in RUNS.values() if r.status == "running" and (ticket_id is None or r.ticket_id == ticket_id)]


def _person(name: str) -> str:
    name = " ".join(name.split())
    if len(name) < 3 or set(re.findall(r"[a-z]+", name.lower())) & AGENT_WORDS:
        raise HTTPException(status_code=400, detail="Type the full name of the person approving, not an agent.")
    return name


async def _pending(ticket_id: int | None = None) -> list[dict[str, Any]]:
    """Everything waiting for a person's approval: proposed payments (invoices, rent) and
    proposed purchase orders, in one shape so the board shows them the same way."""
    proposals = (await mcp("list_payment_proposals"))["proposals"]
    for po in (await mcp("list_purchase_orders", status="proposed"))["purchase_orders"]:
        proposals.append({
            "ticket_id": po["ticket_id"],
            "kind": "purchase",
            "ref_id": po["id"],
            "payee": po.get("vendor"),
            "amount": po["amount"],
            "due_date": None,
            "days_until_due": None,
            "balance_before": po.get("balance_before"),
            "balance_after": po.get("balance_after"),
            "below_cash_buffer": po.get("below_cash_buffer"),
            "cash_buffer": po.get("cash_buffer"),
            "ok": po.get("ok"),
            "problems": po.get("problems") or [],
            "proposal_note": f"PO {po['id']}: {po['qty']} x {po['sku']} size {po['size']} at ${po['unit_cost']:,.2f}",
            "sku": po["sku"],
            "size": po["size"],
            "qty": po["qty"],
            "unit_cost": po["unit_cost"],
            "expected_arrival": po.get("expected_arrival"),
        })
    return [p for p in proposals if ticket_id is None or p["ticket_id"] == ticket_id]


async def _resolve(ticket_id: int, author: str, note: str, how: str) -> None:
    """Mark a ticket resolved with a signed note, and record it in the audit trail."""
    await mcp("add_ticket_note", ticket_id=ticket_id, author=author, note=note[:500], new_status="resolved")
    audit.event(None, "ticket_resolved", ticket_id=ticket_id, by=author, how=how)


# --- The audit trail, read back -------------------------------------------------------------


def _read_audit() -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    with audit._lock:  # never read while a record is half written
        return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


def _last_run(records: list[dict[str, Any]], ticket_id: int) -> dict[str, Any] | None:
    """The latest agent run on a ticket since the last reset, rebuilt from the audit trail
    (so it survives a backend restart). Runs from before a reset no longer count."""
    reset_at = max((i for i, r in enumerate(records) if r.get("event") == "database_reset"), default=-1)
    starts = [r for r in records[reset_at + 1:] if r.get("event") == "task_start" and r.get("ticket_id") == ticket_id]
    if not starts:
        return None
    start = starts[-1]
    task_id = start["task_id"]
    mine = [r for r in records if r.get("task_id") == task_id]
    end = next((r for r in reversed(mine) if r.get("event") == "task_end"), None)
    ends = [r for r in mine if r.get("event") == "agent_end"]
    boss = next((r for r in reversed(ends) if r.get("depth") == 0), None)
    run = RUNS.get(task_id)
    if run and run.status == "running":
        status = "running"
    elif end is None:
        status = "interrupted"  # the backend stopped while it ran
    else:
        status = "finished" if end.get("stop_reason") == "final_answer" else "failed"
    pick = ("agent", "depth", "status", "summary", "actions_taken", "approvals_needed", "customer_message", "time")
    return {
        "task_id": task_id,
        "started": start.get("time"),
        "dry_run": bool(start.get("dry_run")),
        "status": status,
        "stop_reason": end.get("stop_reason") if end else None,
        "error": end.get("error") if end else None,
        "usage": end.get("team_usage") if end else None,
        "delegations": end.get("delegations") if end else None,
        "duration_ms": end.get("duration_ms") if end else None,
        "report": {k: boss.get(k) for k in pick if k in boss} if boss else None,
        "agents": [{k: r.get(k) for k in pick if r.get(k) is not None} for r in ends],
    }


def _desk_state(ticket: dict[str, Any], last_run: dict[str, Any] | None, pending: list[dict[str, Any]]) -> DeskState:
    if not ticket["open"]:
        return "resolved"
    if last_run and last_run["status"] == "running":
        return "running"
    if pending:
        return "awaiting_approval"
    if last_run and not last_run["dry_run"]:
        if last_run["status"] in ("failed", "interrupted"):
            return "needs_attention"
        boss_status = (last_run.get("report") or {}).get("status")
        if boss_status == "needs_approval":
            return "needs_signoff"
        if boss_status in ("blocked", "needs_info"):
            return "needs_attention"
    return "open"


# --- Tickets and runs ---------------------------------------------------------------------


@app.get("/")
def index() -> dict[str, Any]:
    return {
        "app": "Campus Customs backend",
        "docs": "/docs",
        "routes": [f"{', '.join(sorted(r.methods - {'HEAD'}))} {r.path}" for r in app.routes
                   if getattr(r, "methods", None) and r.path.startswith("/api")],
    }


@app.get("/api/tickets")
async def list_tickets() -> dict[str, Any]:
    """Every ticket: open or resolved, its urgency, where it stands on the desk, and its latest run."""
    data = await mcp("list_tickets")
    pending = await _pending()
    records = _read_audit()
    tickets = []
    for t in data["tickets"]:
        urgency = await mcp("get_ticket_urgency", ticket_id=t["id"])
        mine = [p for p in pending if p["ticket_id"] == t["id"]]
        last_run = _last_run(records, t["id"])
        tickets.append({
            **t,
            "state": "open" if t["open"] else "resolved",
            "desk_state": _desk_state(t, last_run, mine),
            "urgency": {k: urgency.get(k) for k in ("urgency", "deadline", "deadline_source", "days_until_deadline", "reply_by")},
            "pending_payments": mine,
            "last_run": last_run,
        })
    return {"shop_date": data["shop_date"], "tickets": tickets}


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int, dry_run: bool = False) -> dict[str, Any]:
    """Start the agent team on one ticket. Returns at once; follow it with /api/events or /api/runs."""
    ticket = await mcp("get_ticket", ticket_id=ticket_id)
    if not ticket.get("found"):
        raise HTTPException(status_code=404, detail=f"No ticket with id {ticket_id}.")
    if ticket["status"] in CLOSED:
        raise HTTPException(status_code=409, detail=f"Ticket {ticket_id} is already {ticket['status']}.")
    if _running(ticket_id):
        raise HTTPException(status_code=409, detail=f"The team is already working on ticket {ticket_id}.")
    try:
        team = Team(dry_run=dry_run)
    except MissingAPIKeyError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err

    run = Run(task_id=new_id("task"), ticket_id=ticket_id, dry_run=dry_run, started=audit.now())
    RUNS[run.task_id] = run

    async def work() -> None:
        try:
            run.result = await team.run_task(
                TICKET_TASK.format(ticket_id=ticket_id),
                "boss",
                task_id=run.task_id,
                meta={"ticket_id": ticket_id, "started_by": "dashboard"},
            )
            run.status = "finished" if run.result.stop_reason == "final_answer" else "failed"
            run.error = run.result.error
            report = run.result.report
            # The desk rule: a finished, saved run with nothing left for a person resolves the ticket.
            if run.status == "finished" and not dry_run and report and report.status == "done":
                still_open = (await mcp("get_ticket", ticket_id=ticket_id))["status"] not in CLOSED
                if still_open and not await _pending(ticket_id):
                    await _resolve(ticket_id, "boss", f"Resolved: the team finished with nothing waiting. {report.summary}",
                                   how="run finished")
                    run.resolved_by_run = True
        except Exception as err:  # noqa: BLE001 - reported through /api/runs
            run.status, run.error = "failed", f"{type(err).__name__}: {err}"

    run.job = asyncio.create_task(work())
    return {
        "task_id": run.task_id,
        "ticket_id": ticket_id,
        "dry_run": dry_run,
        "status": run.status,
        "follow": {"events": f"/api/events?task_id={run.task_id}", "run": f"/api/runs/{run.task_id}"},
    }


class SourceRequest(BaseModel):
    source: Literal["online", "in_person", "phone"] | None = Field(
        description="Where the ticket came from: online submission, in person, or phone (called in); null = not recorded"
    )


@app.post("/api/tickets/{ticket_id}/source")
async def set_source(ticket_id: int, body: SourceRequest) -> dict[str, Any]:
    """Record where a ticket came from (or clear it)."""
    result = await mcp("set_ticket_source", ticket_id=ticket_id, source=body.source)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"No ticket with id {ticket_id}.")
    return {"ticket_id": ticket_id, "source": result["source"]}


class ResolveRequest(BaseModel):
    approved_by: str = Field(description="Full name of the person signing off")
    note: str | None = Field(default=None, max_length=300, description="Optional reason, saved on the ticket")


@app.post("/api/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, body: ResolveRequest) -> dict[str, Any]:
    """A person signs off a ticket the team has finished (no payment may be waiting)."""
    name = _person(body.approved_by)
    ticket = await mcp("get_ticket", ticket_id=ticket_id)
    if not ticket.get("found"):
        raise HTTPException(status_code=404, detail=f"No ticket with id {ticket_id}.")
    if ticket["status"] in CLOSED:
        raise HTTPException(status_code=409, detail=f"Ticket {ticket_id} is already {ticket['status']}.")
    if _running(ticket_id):
        raise HTTPException(status_code=409, detail="Wait for the team to finish this ticket first.")
    if await _pending(ticket_id):
        raise HTTPException(status_code=409, detail="A payment or purchase on this ticket is waiting for approval; approve it first.")
    note = f"Signed off and resolved by {name}." + (f" {' '.join(body.note.split())}" if body.note else "")
    await _resolve(ticket_id, name, note, how="signed off")
    return {"ticket_id": ticket_id, "status": "resolved", "resolved_by": name}


@app.get("/api/runs/{task_id}")
def get_run(task_id: str) -> dict[str, Any]:
    run = RUNS.get(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No run {task_id} since the backend started.")
    return {
        "task_id": run.task_id,
        "ticket_id": run.ticket_id,
        "dry_run": run.dry_run,
        "started": run.started,
        "status": run.status,
        "error": run.error,
        "resolved_by_run": run.resolved_by_run,
        "result": run.result.model_dump(exclude_none=True) if run.result else None,
    }


# --- Agent events (from the audit trail) ----------------------------------------------------


def _readable(seq: int, r: dict[str, Any]) -> dict[str, Any]:
    """One audit record as the board shows it: who, what they said, which tools they used."""
    e: dict[str, Any] = {
        "seq": seq,
        "time": r.get("time"),
        "event": r.get("event"),
        "task_id": r.get("task_id"),
        "agent": r.get("agent"),
        "depth": r.get("depth"),
        "step": r.get("step"),
    }
    kind = r.get("event")
    if kind == "task_start":
        e.update(ticket_id=r.get("ticket_id"), said=r.get("task"), dry_run=r.get("dry_run"))
    elif kind == "agent_start":
        chain = r.get("chain") or []
        e.update(asked_by=chain[-2] if len(chain) > 1 else "manager", said=r.get("task"))
    elif kind == "model_response":
        calls = r.get("tool_calls", [])
        tools = [{"tool": c["tool"], "call_id": c.get("call_id"), "args": c.get("args", {})}
                 for c in calls if c["tool"] != "final_result"]
        final = next((c for c in calls if c["tool"] == "final_result"), None)
        said = " ".join(r.get("text", [])) or (final["args"].get("summary") if final else None)
        e.update(tools=tools, said=said, final=final is not None or None, tokens=r.get("tokens"))
    elif kind == "model_request":
        e.update(tool_results=r.get("tool_results", []), retries=r.get("retries"))
    elif kind == "agent_end":
        e.update(said=r.get("summary"), status=r.get("status"), ticket_ids=r.get("ticket_ids"),
                 approvals_needed=r.get("approvals_needed"), actions_taken=r.get("actions_taken"),
                 customer_message=r.get("customer_message"))
    elif kind == "agent_error":
        e.update(said=r.get("error"))
    elif kind == "delegation_refused":
        e.update(to=r.get("to"), said=r.get("reason"))
    elif kind == "task_end":
        e.update(ticket_id=r.get("ticket_id"), stop_reason=r.get("stop_reason"), status=r.get("report_status"),
                 usage=r.get("team_usage"), said=r.get("error"))
    else:  # payment_approved, ticket_resolved, database_reset, ...
        e.update({k: v for k, v in r.items() if k not in e})
    return {k: v for k, v in e.items() if v is not None}


@app.get("/api/events")
def list_events(
    limit: int = Query(50, ge=1, le=500),
    after: int = Query(-1, description="only events with seq greater than this (for refreshing)"),
    task_id: str | None = None,
    ticket_id: int | None = None,
    raw: bool = Query(False, description="return the full audit records"),
) -> dict[str, Any]:
    """The most recent agent events, oldest first. Poll with after=<last_seq> to get only new ones."""
    records = _read_audit()
    if ticket_id is not None:
        tasks = {r["task_id"] for r in records if r.get("event") == "task_start" and r.get("ticket_id") == ticket_id}
        if task_id:
            tasks &= {task_id}
        picked = [(i, r) for i, r in enumerate(records) if r.get("task_id") in tasks]
    else:
        picked = [(i, r) for i, r in enumerate(records) if not task_id or r.get("task_id") == task_id]
    picked = [(i, r) for i, r in picked if i > after][-limit:]
    return {
        "last_seq": len(records) - 1,
        "events": [({"seq": i, **r} if raw else _readable(i, r)) for i, r in picked],
    }


# --- Payments: a person approves, and only then does cash change ------------------------------


class ApproveRequest(BaseModel):
    ticket_id: int
    approved_by: str = Field(description="Full name of the person approving")
    kind: Literal["invoice", "rent", "purchase"] | None = Field(
        default=None, description="Only needed if a ticket has two proposals"
    )
    ref_id: int | None = Field(default=None, description="Invoice id, lease id, or purchase order id")


@app.get("/api/payments/pending")
async def pending_payments() -> dict[str, Any]:
    """Payments and purchases the agents proposed (vendor invoices, rent, purchase orders)
    that are waiting for a person."""
    proposals = await _pending()
    return {"count": len(proposals), "proposals": proposals}


@app.post("/api/payments/approve")
async def approve_payment(body: ApproveRequest) -> dict[str, Any]:
    """A person approves a payment or purchase the agents proposed. This is the only route that changes cash.

    If it was the last approval waiting on a ticket whose run has finished, the ticket is resolved.
    """
    name = _person(body.approved_by)
    matches = [
        p for p in await _pending(body.ticket_id)
        if (body.kind is None or p["kind"] == body.kind) and (body.ref_id is None or p["ref_id"] == body.ref_id)
    ]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Nothing is waiting for approval on ticket {body.ticket_id}.")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="This ticket has more than one proposal; say which kind and ref_id.")
    proposal = matches[0]

    if proposal["kind"] == "purchase":
        bought = await mcp("record_purchase", po_id=proposal["ref_id"], approved_by=name)
        if not bought.get("purchased"):
            raise HTTPException(status_code=409, detail={"message": "The purchase failed its checks.", "problems": bought.get("problems")})
        paid = {
            "paid": True, "kind": "purchase", "ref_id": bought["po_id"], "payment_id": bought["payment_id"],
            "payee": bought["vendor"], "amount": bought["amount"], "approved_by": bought["approved_by"],
            "balance_after": bought["balance_after"], "below_cash_buffer": bought["below_cash_buffer"],
            "expected_arrival": bought["expected_arrival"],
            "what": f"{bought['qty']} x {bought['sku']} size {bought['size']}",
        }
    else:
        paid = await mcp("record_payment", kind=proposal["kind"], ref_id=proposal["ref_id"],
                         amount=proposal["amount"], approved_by=name)
        if not paid.get("paid"):
            raise HTTPException(status_code=409, detail={"message": "The payment failed its checks.", "problems": paid.get("problems")})
    audit.event(None, "payment_approved", ticket_id=body.ticket_id, approved_by=paid["approved_by"],
                kind=paid["kind"], ref_id=paid["ref_id"], amount=paid["amount"], payee=paid["payee"],
                payment_id=paid["payment_id"], balance_after=paid["balance_after"])

    last_run = _last_run(_read_audit(), body.ticket_id)
    ticket = await mcp("get_ticket", ticket_id=body.ticket_id)
    resolved = False
    if (ticket["status"] not in CLOSED and last_run and last_run["status"] == "finished"
            and not last_run["dry_run"] and not await _pending(body.ticket_id)):
        await _resolve(body.ticket_id, name,
                       f"Resolved after {name} approved the ${paid['amount']:,.2f} {'purchase from' if paid['kind'] == 'purchase' else 'payment to'} {paid['payee']}.",
                       how="payment approved")
        resolved = True
    return {**paid, "ticket_resolved": resolved}


@app.get("/api/cash")
async def cash() -> dict[str, Any]:
    """The checking balance from cash_accounts, with the shop's date and the cash buffer."""
    data = await mcp("get_cash_balance")
    checking = next((a for a in data["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(status_code=404, detail="There is no checking account in cash_accounts.")
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "shop_date": data["shop_date"],
        "cash_buffer": data["cash_buffer"],
        "below_buffer": checking["balance"] < data["cash_buffer"],
    }


# --- Reset --------------------------------------------------------------------------------


class ResetRequest(BaseModel):
    confirm: bool = Field(False, description="Must be true: this undoes every change to the working database")


@app.post("/api/reset")
async def reset(body: ResetRequest) -> dict[str, Any]:
    """Put data/campus_customs_new.db back to the original values for a fresh run (MCP reset_working_copy).

    The audit trail is kept (it is never wiped); a database_reset record is added to it.
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail='Send {"confirm": true} to reset the working database.')
    if _running():
        raise HTTPException(status_code=409, detail="Wait for the running agent tasks to finish before resetting.")
    done = await mcp("reset_working_copy", confirm=True)  # through the MCP server, like every other change
    audit.event(None, "database_reset", source=done["source"], target=done["target"])
    return {"reset": True, "tickets": done["tickets"], "checking_balance": done["checking_balance"]}
