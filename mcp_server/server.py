"""Campus Customs MCP server: the shared tools every Homework 5 agent uses.

Works on the shop's working database, data/campus_customs_new.db (one folder up from
this file). The original data/campus_customs.db is never touched. Every tool returns
only what is in the database; when a row is missing it says found = false instead of
guessing.

The shop's "today" is desk.date_today in the database, not the computer's clock.

Most tools only read. The ones that write:
    add_ticket_note, propose_payment, propose_purchase_order   agents may use these; they move no money
    set_ticket_source                                          the desk (a person) records where a ticket came from
    record_payment, record_purchase                            move money: a human manager only. The agent team
                                                               is never given them, and they refuse an approver
                                                               that names an agent.
A vendor ships nothing new while it has an unpaid invoice with us (get_vendor_lead_time
reports it as on_hold, and the purchase tools refuse to buy from it).

Environment (optional)
    CAMPUS_CUSTOMS_DB          another database file to use (for tests)
    CAMPUS_CUSTOMS_READ_ONLY   "1" = dry run: write tools report what they would do
                               and change nothing

Run (stdio):  python server.py
"""

from __future__ import annotations

import calendar
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DB") or HERE.parent / "data" / "campus_customs_new.db")
READ_ONLY = os.environ.get("CAMPUS_CUSTOMS_READ_ONLY") == "1"

mcp = FastMCP("campus-customs")

# A deadline this many days away or fewer (but not past) counts as due_soon.
DUE_SOON_DAYS = 3
# Inquiries (price requests, questions) must get a reply within this many hours of coming in,
# so the shop doesn't lose the business by answering slowly.
INQUIRY_TYPES = ("price_override", "inquiry", "question")
INQUIRY_REPLY_HOURS = 24
# Where a ticket came from. Blank (NULL) means it wasn't recorded.
TICKET_SOURCES = ("online", "in_person", "phone")

# Shop rules the tools enforce. These must match backend/prompts/shop_rules.md.
BULK_MIN_QTY = 12  # units of one product before a bulk discount can be offered
AGENT_DISCOUNT_LIMIT_PCT = 10  # Accounting may offer up to this on a bulk order by itself
MAX_DISCOUNT_PCT = 20  # never more than this, even with a manager's approval
CASH_BUFFER = 500.0  # flag any payment that leaves checking below this

# Ticket statuses. A ticket counts as open until it is resolved or closed.
TICKET_STATUSES = (
    "open",
    "in_progress",
    "awaiting_approval",
    "waiting_on_stock",
    "waiting_on_customer",
    "resolved",
    "closed",
)
CLOSED_STATUSES = ("resolved", "closed")
PAYMENT_KINDS = ("invoice", "rent")
MAX_NOTE_CHARS = 500
# Only the payment and purchase tools write notes that start with these, so a plain note
# can't pass itself off as a proposal, a payment or a purchase.
RESERVED_NOTE_PREFIXES = ("PAYMENT PROPOSED", "PAID", "PURCHASE PROPOSED", "PURCHASED")
# How propose_payment writes a proposal; list_payment_proposals reads it back.
PROPOSAL_PATTERN = re.compile(
    r"PAYMENT PROPOSED: \$(?P<amount>[\d,]+\.\d{2}) to (?P<payee>.+?) for (?P<kind>invoice|rent) (?P<ref_id>\d+) from"
)
# An approver whose name contains one of these words is an agent, not a person.
AGENT_WORDS = {"boss", "inventory", "accounting", "facilities", "customer", "service",
               "agent", "assistant", "bot", "system", "llm", "gpt"}
# Rent due further out than this has most likely been paid for the current month already.
RENT_EARLIEST_DAYS = 30


@contextmanager
def _connect(write: bool = False) -> Iterator[sqlite3.Connection]:
    # Read tools open the file read-only so they can never change the shop's data. Write
    # tools open it read-write but never create it, and commit only if nothing failed.
    mode = "rw" if write else "ro"
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if write:
            with conn:
                yield conn
        else:
            yield conn
    finally:
        conn.close()


def _money(value: float) -> float:
    return round(value + 0.0, 2)


def _add_month(day: date) -> date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def _ticket_note(conn: sqlite3.Connection, ticket_id: int, author: str, note: str,
                 new_status: str | None = None) -> str:
    """Append a dated line to a ticket's notes (and change its status). Caller commits."""
    line = f"[{_shop_today(conn).isoformat()} {author}] {note}"
    conn.execute(
        "UPDATE tickets SET notes = COALESCE(notes || char(10), '') || ?, status = COALESCE(?, status) WHERE id = ?",
        (line, new_status, ticket_id),
    )
    return line


def _shop_today(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None or not row["date_today"]:
        raise ToolError("The desk table has no date_today, so the shop's date is unknown.")
    return date.fromisoformat(row["date_today"])


@mcp.tool
def check_stock(sku: str, size: str) -> dict:
    """Check how many units of a product are on the shelf in one size.

    Use before promising a customer order or a bulk request. `sku` is the product
    code (for example "CC-TEE-WHITE"); `size` is S, M, L, XL, or OS for one-size items.

    Returns the product name, units on hand (qty), in_stock (qty > 0) and aisle for
    that size, plus all_sizes with the count for every size of the product, from the
    inventory table. If the product or size is not stocked, returns found = false.
    Never guess a count that is not returned here.
    """
    sku, size = sku.strip().upper(), size.strip().upper()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name, size, qty, location FROM inventory WHERE sku = ? ORDER BY rowid",
            (sku,),
        ).fetchall()
    if not rows:
        return {"found": False, "sku": sku, "size": size, "message": f"No product {sku} in inventory."}

    all_sizes = {r["size"]: r["qty"] for r in rows}
    match = next((r for r in rows if r["size"] == size), None)
    if match is None:
        return {
            "found": False,
            "sku": sku,
            "size": size,
            "name": rows[0]["name"],
            "message": f"{sku} is not stocked in size {size}.",
            "all_sizes": all_sizes,
        }
    return {
        "found": True,
        "sku": sku,
        "name": match["name"],
        "size": size,
        "qty": match["qty"],
        "in_stock": match["qty"] > 0,
        "location": match["location"],
        "all_sizes": all_sizes,
    }


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """Look up a lease to confirm a rent notice before anyone pays it.

    Use for rent tickets: the ticket's lease_id points to the lease. Returns the space,
    landlord, monthly rent and next due date from the leases table, plus the shop's
    date (desk.date_today) and days_until_due from that date (negative means overdue).
    Compare the landlord and amount with the notice; if the lease does not exist,
    returns found = false.
    """
    with _connect() as conn:
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        today = _shop_today(conn)
    if lease is None:
        return {"found": False, "lease_id": lease_id, "message": f"No lease with id {lease_id}."}
    return {
        "found": True,
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": lease["monthly_rent"],
        "next_due": lease["next_due"],
        "notes": lease["notes"],
        "shop_date": today.isoformat(),
        "days_until_due": (date.fromisoformat(lease["next_due"]) - today).days,
    }


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Get a product's list price and unit cost, for quotes and discount requests.

    `sku` is the product code (for example "CC-HOOD-NAVY"). Returns list_price (what
    the shop charges), unit_cost (what the shop pays) and margin_per_unit (list_price
    minus unit_cost) from the pricing table. Any discount must keep the price above
    unit_cost. If the product has no price, returns found = false; never quote a
    price that is not returned here.
    """
    sku = sku.strip().upper()
    with _connect() as conn:
        row = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "message": f"No price for {sku} in the pricing table."}
    return {
        "found": True,
        "sku": sku,
        "list_price": row["list_price"],
        "unit_cost": row["unit_cost"],
        "margin_per_unit": round(row["list_price"] - row["unit_cost"], 2),
    }


@mcp.tool
def get_ticket_urgency(ticket_id: int) -> dict:
    """Rate how urgent a ticket is from the due dates it links to, by a fixed rule.

    Follows the ticket's invoice_id (the invoice's due_date, if the invoice is still
    open) and lease_id (the lease's next_due). Inquiries (price requests and questions)
    also get a reply-by deadline 24 hours after they came in (reply_by). The earliest of
    these dates is the deadline. Days are counted from the shop's date (desk.date_today).
    Urgency is:
      overdue      the deadline has passed
      due_soon     0-3 days left
      upcoming     more than 3 days left
      no_deadline  the ticket links to no open invoice or lease, so the database has no due date
      not_open     the ticket is resolved or closed
    Also returns days_open (days since the ticket was created). Use it to decide which
    ticket to handle first; it never makes up a deadline that is not in the database.
    """
    with _connect() as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
        today = _shop_today(conn)

        deadlines: list[tuple[date, str]] = []
        if ticket["invoice_id"] is not None:
            invoice = conn.execute(
                "SELECT due_date, status FROM invoices WHERE id = ?", (ticket["invoice_id"],)
            ).fetchone()
            if invoice is not None and invoice["status"] == "open":
                deadlines.append(
                    (date.fromisoformat(invoice["due_date"]), f"invoice {ticket['invoice_id']} due date")
                )
        if ticket["lease_id"] is not None:
            lease = conn.execute(
                "SELECT next_due FROM leases WHERE id = ?", (ticket["lease_id"],)
            ).fetchone()
            if lease is not None:
                deadlines.append(
                    (date.fromisoformat(lease["next_due"]), f"lease {ticket['lease_id']} rent due date")
                )
        reply_by = None
        if ticket["type"] in INQUIRY_TYPES:
            reply_by = datetime.fromisoformat(ticket["created_at"]) + timedelta(hours=INQUIRY_REPLY_HOURS)
            deadlines.append((reply_by.date(), f"{INQUIRY_REPLY_HOURS}-hour reply window for inquiries"))

    result = {
        "found": True,
        "ticket_id": ticket["id"],
        "type": ticket["type"],
        "subject": ticket["subject"],
        "ticket_status": ticket["status"],
        "shop_date": today.isoformat(),
        "days_open": (today - datetime.fromisoformat(ticket["created_at"]).date()).days,
        "deadline": None,
        "deadline_source": None,
        "days_until_deadline": None,
        "reply_by": reply_by.isoformat() if reply_by else None,
    }
    if deadlines:
        deadline, source = min(deadlines)
        days_left = (deadline - today).days
        result.update(
            deadline=deadline.isoformat(), deadline_source=source, days_until_deadline=days_left
        )

    if ticket["status"] in CLOSED_STATUSES:
        result["urgency"] = "not_open"
    elif not deadlines:
        result["urgency"] = "no_deadline"
    elif days_left < 0:
        result["urgency"] = "overdue"
    elif days_left <= DUE_SOON_DAYS:
        result["urgency"] = "due_soon"
    else:
        result["urgency"] = "upcoming"
    return result


def _unpaid_invoices(conn: sqlite3.Connection, vendor_id: int) -> list[dict]:
    """A vendor's invoices that are not paid yet. While there are any, it ships nothing new."""
    rows = conn.execute(
        "SELECT id, amount, due_date, description FROM invoices WHERE vendor_id = ? AND status != 'paid' ORDER BY id",
        (vendor_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _vendor_view(conn: sqlite3.Connection, vendor: sqlite3.Row, today: date) -> dict:
    unpaid = _unpaid_invoices(conn, vendor["id"])
    arrival = (today + timedelta(days=vendor["lead_days"])).isoformat()
    view = {
        "vendor_id": vendor["id"],
        "name": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "on_hold": bool(unpaid),
        "unpaid_invoices": unpaid,
        "earliest_arrival": None if unpaid else arrival,
    }
    if unpaid:
        ids = ", ".join(str(i["id"]) for i in unpaid)
        view["hold_reason"] = (
            f"{vendor['name']} has unpaid invoice {ids}, so it ships nothing new until that is paid."
        )
        view["earliest_arrival_after_payment"] = (
            f"{vendor['lead_days']} days after invoice {ids} is paid ({arrival} if paid on the shop's date)"
        )
    return view


@mcp.tool
def get_vendor_lead_time(vendor_id: int | None = None, specialty: str | None = None) -> dict:
    """How long a vendor takes to deliver, whether it is on hold, and the earliest arrival.

    Pass vendor_id when a ticket's invoice names the vendor, or a specialty word
    ("apparel", "mugs", "courier") to find vendors when none is linked; vendor_id wins
    if both are given. Returns each matching vendor's name, specialty and lead_days,
    fastest first. **A vendor ships nothing new while it has an unpaid invoice with us**:
    then on_hold is true, unpaid_invoices lists them, earliest_arrival is null and
    earliest_arrival_after_payment says when stock could come once they are paid.
    Otherwise earliest_arrival is desk.date_today plus lead_days (calendar days). If no
    vendor matches, returns found = false.
    """
    if vendor_id is None and not (specialty and specialty.strip()):
        raise ToolError("Pass a vendor_id or a specialty word to look up.")
    with _connect() as conn:
        today = _shop_today(conn)
        if vendor_id is not None:
            rows = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM vendors WHERE specialty LIKE ? ORDER BY lead_days, id",
                (f"%{specialty.strip()}%",),
            ).fetchall()
        if not rows:
            lookup = f"id {vendor_id}" if vendor_id is not None else f"specialty '{specialty.strip()}'"
            return {"found": False, "message": f"No vendor with {lookup}."}
        vendors = [_vendor_view(conn, r, today) for r in rows]
    return {"found": True, "shop_date": today.isoformat(), "vendors": vendors}


# --- Tickets ----------------------------------------------------------------------------


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not resolved or closed, oldest first, with the shop's date.

    Start here to see the work queue. Each ticket shows its id, type, requester, subject,
    status and when it came in; call get_ticket for the full details and links.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        rows = conn.execute(
            "SELECT id, type, requester, subject, status, created_at FROM tickets "
            f"WHERE status NOT IN ({','.join('?' * len(CLOSED_STATUSES))}) ORDER BY created_at, id",
            CLOSED_STATUSES,
        ).fetchall()
    return {"shop_date": today.isoformat(), "count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool
def list_tickets() -> dict:
    """List every ticket, including resolved and closed ones, with open = true or false.

    For dashboards and reports that need the whole board. Each ticket has every column
    (request, links, status, notes); open is false once a ticket is resolved or closed.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    tickets = [{"source": None, **dict(r), "open": r["status"] not in CLOSED_STATUSES} for r in rows]
    return {"shop_date": today.isoformat(), "count": len(tickets), "tickets": tickets}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Read one ticket in full: the request, its linked product, lease or invoice, status and notes.

    sku, size and qty name the product a customer asked about (check_stock, get_pricing,
    quote_bulk_price); lease_id links a rent notice to get_lease; invoice_id links a vendor
    bill to get_invoice. notes holds the original request plus every note the team added.
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
    return {"found": True, "source": None, **dict(row)}


@mcp.tool
def set_ticket_source(ticket_id: int, source: str | None) -> dict:
    """Record where a ticket came from: "online", "in_person" or "phone" (called in); null clears it.

    The tickets table gets a source column the first time this is used (the original
    database doesn't have one), so a ticket with no recorded source shows source = null.
    For people at the desk; the agents are not given this tool.
    """
    if source is not None and source not in TICKET_SOURCES:
        raise ToolError(f"source must be one of: {', '.join(TICKET_SOURCES)}, or null.")
    with _connect(write=not READ_ONLY) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
        if READ_ONLY:
            return {"found": True, "written": False, "dry_run": True, "ticket_id": ticket_id, "source": source}
        if "source" not in {c["name"] for c in conn.execute("PRAGMA table_info(tickets)")}:
            conn.execute("ALTER TABLE tickets ADD COLUMN source TEXT")
        conn.execute("UPDATE tickets SET source = ? WHERE id = ?", (source, ticket_id))
    return {"found": True, "written": True, "ticket_id": ticket_id, "source": source}


@mcp.tool
def add_ticket_note(ticket_id: int, author: str, note: str, new_status: str | None = None) -> dict:
    """Add a dated note to a ticket and optionally change its status. Notes are never edited or removed.

    `author` is who is writing (your role, for example "inventory"). Keep the note to one or
    two sentences of facts and decisions (500 characters at most). new_status, if given,
    must be one of: open, in_progress, awaiting_approval, waiting_on_stock,
    waiting_on_customer, resolved, closed.
    """
    author, note = " ".join(author.split()), " ".join(note.split())
    if not author or not note:
        raise ToolError("author and note are both required.")
    if len(note) > MAX_NOTE_CHARS:
        raise ToolError(f"The note is {len(note)} characters; keep it to {MAX_NOTE_CHARS}.")
    if new_status is not None and new_status not in TICKET_STATUSES:
        raise ToolError(f"new_status must be one of: {', '.join(TICKET_STATUSES)}.")
    if note.upper().startswith(RESERVED_NOTE_PREFIXES):
        raise ToolError("Notes starting with PAYMENT PROPOSED, PAID, PURCHASE PROPOSED or PURCHASED are written only by the payment and purchase tools.")

    with _connect(write=not READ_ONLY) as conn:
        row = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
        if READ_ONLY:
            line = f"[{_shop_today(conn).isoformat()} {author}] {note}"
            return {"found": True, "written": False, "dry_run": True, "ticket_id": ticket_id,
                    "would_add_note": line, "status": new_status or row["status"]}
        line = _ticket_note(conn, ticket_id, author, note, new_status)
    return {"found": True, "written": True, "ticket_id": ticket_id, "note": line,
            "status": new_status or row["status"]}


# --- Money ------------------------------------------------------------------------------


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """Read a vendor invoice: amount, due date, status, the vendor, and payments made on it.

    Use for a bill linked to a ticket (the ticket's invoice_id). Returns days_until_due from
    the shop's date (negative = overdue), the vendor's name, specialty and lead days, every
    payment already recorded against the invoice, and amount_outstanding. An unpaid restock
    invoice means that restock cannot be counted on yet.
    """
    with _connect() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if invoice is None:
            return {"found": False, "invoice_id": invoice_id, "message": f"No invoice with id {invoice_id}."}
        today = _shop_today(conn)
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (invoice["vendor_id"],)).fetchone()
        payments = conn.execute(
            "SELECT id, amount, account, paid_at, approved_by FROM payments "
            "WHERE kind = 'invoice' AND ref_id = ? ORDER BY id",
            (invoice_id,),
        ).fetchall()
    paid = sum(p["amount"] for p in payments)
    days_left = (date.fromisoformat(invoice["due_date"]) - today).days
    is_paid = invoice["status"] == "paid"
    return {
        "found": True,
        "invoice_id": invoice["id"],
        "amount": invoice["amount"],
        "due_date": invoice["due_date"],
        "status": invoice["status"],
        "description": invoice["description"],
        "shop_date": today.isoformat(),
        "days_until_due": days_left,
        "overdue": not is_paid and days_left < 0,
        "vendor": dict(vendor) if vendor else None,
        "payments": [dict(p) for p in payments],
        "amount_paid": _money(paid),
        "amount_outstanding": 0.0 if is_paid else _money(invoice["amount"] - paid),
    }


@mcp.tool
def get_cash_balance() -> dict:
    """Cash in each shop account, with the shop's date and the cash buffer rule.

    Check this before proposing any payment. cash_buffer is the balance the shop keeps in
    checking; a payment that would leave less than that must be flagged for a human.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        rows = conn.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name").fetchall()
    return {
        "shop_date": today.isoformat(),
        "accounts": [dict(r) for r in rows],
        "total": _money(sum(r["balance"] for r in rows)),
        "cash_buffer": CASH_BUFFER,
    }


@mcp.tool
def quote_bulk_price(sku: str, qty: int, discount_pct: float = 0) -> dict:
    """Price `qty` units of a product at an optional discount and say whether the shop rules allow it.

    Reads the pricing table and works out the unit and total price, the shop's cost and the
    margin. It changes nothing. decision is:
      allowed               list price, or a bulk discount (12+ units) of 10% or less
      needs_human_approval  a bulk discount over 10% and up to 20%, or any discount under 12 units
      not_allowed           over 20% off, or a unit price at or below the shop's unit cost
    Quote customers only numbers this tool returns.
    """
    sku = sku.strip().upper()
    if qty < 1:
        raise ToolError("qty must be at least 1.")
    if not 0 <= discount_pct <= 100:
        raise ToolError("discount_pct must be between 0 and 100.")
    with _connect() as conn:
        row = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "message": f"No price for {sku} in the pricing table."}

    list_price, unit_cost = row["list_price"], row["unit_cost"]
    unit_price = _money(list_price * (1 - discount_pct / 100))
    bulk = qty >= BULK_MIN_QTY
    if unit_price <= unit_cost:
        decision, reason = "not_allowed", f"${unit_price:.2f} is at or below the ${unit_cost:.2f} unit cost."
    elif discount_pct > MAX_DISCOUNT_PCT:
        decision, reason = "not_allowed", f"The shop never discounts more than {MAX_DISCOUNT_PCT}%."
    elif discount_pct == 0:
        decision, reason = "allowed", "List price."
    elif not bulk:
        decision, reason = "needs_human_approval", f"Discounts on fewer than {BULK_MIN_QTY} units need a manager."
    elif discount_pct <= AGENT_DISCOUNT_LIMIT_PCT:
        decision, reason = "allowed", f"Bulk order of {BULK_MIN_QTY}+ units, discount within {AGENT_DISCOUNT_LIMIT_PCT}%."
    else:
        decision, reason = "needs_human_approval", f"Bulk discounts over {AGENT_DISCOUNT_LIMIT_PCT}% need a manager."

    quote_total = _money(unit_price * qty)
    cost_total = _money(unit_cost * qty)
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "discount_pct": discount_pct,
        "list_price": list_price,
        "unit_price": unit_price,
        "unit_cost": unit_cost,
        "list_total": _money(list_price * qty),
        "quote_total": quote_total,
        "discount_amount": _money(list_price * qty - quote_total),
        "cost_total": cost_total,
        "margin_total": _money(quote_total - cost_total),
        "margin_pct": round(100 * (unit_price - unit_cost) / unit_price, 1) if unit_price else None,
        "decision": decision,
        "reason": reason,
        "rules": {
            "bulk_min_qty": BULK_MIN_QTY,
            "agent_discount_limit_pct": AGENT_DISCOUNT_LIMIT_PCT,
            "max_discount_pct": MAX_DISCOUNT_PCT,
        },
    }


def _payment_check(conn: sqlite3.Connection, kind: str, ref_id: int, amount: float, account: str) -> dict:
    """What paying this bill would do, and every reason it cannot be paid right now."""
    if kind not in PAYMENT_KINDS:
        return {"ok": False, "problems": [f"kind must be one of: {', '.join(PAYMENT_KINDS)}."]}
    today = _shop_today(conn)
    problems: list[str] = []
    if kind == "invoice":
        bill = conn.execute(
            "SELECT i.amount, i.due_date, i.status, v.name AS payee FROM invoices i "
            "LEFT JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
            (ref_id,),
        ).fetchone()
        if bill is None:
            return {"ok": False, "problems": [f"No invoice with id {ref_id}."]}
        owed, due = bill["amount"], bill["due_date"]
        if bill["status"] == "paid":
            problems.append(f"Invoice {ref_id} is already paid.")
    else:
        bill = conn.execute(
            "SELECT monthly_rent, next_due, landlord AS payee FROM leases WHERE id = ?", (ref_id,)
        ).fetchone()
        if bill is None:
            return {"ok": False, "problems": [f"No lease with id {ref_id}."]}
        owed, due = bill["monthly_rent"], bill["next_due"]
    days_left = (date.fromisoformat(due) - today).days
    if kind == "rent" and days_left > RENT_EARLIEST_DAYS:
        problems.append(f"Rent on lease {ref_id} is not due until {due}; this month looks paid already.")
    if abs(amount - owed) > 0.005:
        problems.append(f"${amount:,.2f} does not match the ${owed:,.2f} on file.")

    cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    balance = cash["balance"] if cash else None
    after = _money(balance - amount) if cash else None
    if cash is None:
        problems.append(f"No cash account named '{account}'.")
    elif after < 0:
        problems.append(f"Not enough cash: {account} has ${balance:,.2f}.")
    return {
        "ok": not problems,
        "problems": problems,
        "kind": kind,
        "ref_id": ref_id,
        "payee": bill["payee"],
        "amount": _money(amount),
        "amount_on_file": owed,
        "due_date": due,
        "days_until_due": days_left,
        "account": account,
        "balance_before": balance,
        "balance_after": after,
        "below_cash_buffer": after is not None and after < CASH_BUFFER,
        "cash_buffer": CASH_BUFFER,
        "shop_date": today.isoformat(),
    }


@mcp.tool
def propose_payment(ticket_id: int, kind: str, ref_id: int, amount: float, proposed_by: str, reason: str) -> dict:
    """Propose paying a bill, for a human manager to approve. This never moves money.

    kind is "invoice" (ref_id = invoice id) or "rent" (ref_id = lease id), and the ticket
    must link to that invoice or lease. Checks that the bill exists and is unpaid, the
    amount matches what is on file, and checking has the cash, and shows the balance after
    (below_cash_buffer flags a balance under the buffer). If every check passes, adds a
    "PAYMENT PROPOSED" note to the ticket and sets it to awaiting_approval; otherwise
    proposed = false with the problems. Only a person can then pay it.
    """
    proposed_by, reason = " ".join(proposed_by.split()), " ".join(reason.split())[:200]
    if not proposed_by:
        raise ToolError("proposed_by is required.")
    with _connect(write=not READ_ONLY) as conn:
        ticket = conn.execute(
            "SELECT invoice_id, lease_id, notes FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
        check = _payment_check(conn, kind, ref_id, amount, "checking")
        if kind in PAYMENT_KINDS and ticket["invoice_id" if kind == "invoice" else "lease_id"] != ref_id:
            check["problems"].append(f"Ticket {ticket_id} does not link to {kind} {ref_id}.")
            check["ok"] = False
        if check["ok"] and f"PAYMENT PROPOSED: ${check['amount']:,.2f} to {check['payee']} for {kind} {ref_id} " in (
            ticket["notes"] or ""
        ):
            check["problems"].append("This payment is already proposed on the ticket and waiting for a person.")
            check["ok"] = False
        if not check["ok"]:
            return {"proposed": False, "ticket_id": ticket_id, **check}

        note = (
            f"PAYMENT PROPOSED: ${check['amount']:,.2f} to {check['payee']} for {kind} {ref_id} "
            f"from checking, leaving ${check['balance_after']:,.2f}"
            f"{' (BELOW the cash buffer)' if check['below_cash_buffer'] else ''}. "
            f"Reason: {reason or 'not given'}. Awaiting human approval."
        )
        if READ_ONLY:
            return {"proposed": False, "dry_run": True, "ticket_id": ticket_id, "would_add_note": note, **check}
        line = _ticket_note(conn, ticket_id, proposed_by, note, "awaiting_approval")
    return {"proposed": True, "requires_human_approval": True, "ticket_id": ticket_id, "ticket_note": line, **check}


@mcp.tool
def list_payment_proposals() -> dict:
    """List every payment an agent has proposed that is still waiting for a person.

    Reads the "PAYMENT PROPOSED" notes that propose_payment writes on open tickets and keeps
    the ones whose bill is still unpaid. Each proposal has the ticket, kind (invoice or
    rent), ref_id, amount, payee and due date, plus the same checks record_payment will run
    (ok, problems, balance_after, below_cash_buffer) so a person sees them before approving.
    """
    proposals: list[dict] = []
    with _connect() as conn:
        tickets = conn.execute(
            "SELECT id, notes FROM tickets "
            f"WHERE status NOT IN ({','.join('?' * len(CLOSED_STATUSES))}) ORDER BY id",
            CLOSED_STATUSES,
        ).fetchall()
        for ticket in tickets:
            seen: set[tuple[str, int]] = set()
            for line in (ticket["notes"] or "").splitlines():
                match = PROPOSAL_PATTERN.search(line)
                if not match:
                    continue
                kind, ref_id = match["kind"], int(match["ref_id"])
                amount = float(match["amount"].replace(",", ""))
                if (kind, ref_id) in seen:
                    continue
                seen.add((kind, ref_id))
                check = _payment_check(conn, kind, ref_id, amount, "checking")
                already_paid = any("already paid" in p or "looks paid already" in p for p in check["problems"])
                if already_paid:
                    continue
                proposals.append({"ticket_id": ticket["id"], "proposal_note": line, **check})
        today = _shop_today(conn)
    return {"shop_date": today.isoformat(), "count": len(proposals), "proposals": proposals}


@mcp.tool
def record_payment(kind: str, ref_id: int, amount: float, approved_by: str, account: str = "checking") -> dict:
    """HUMAN MANAGER ONLY: pay a bill a person has approved. The agent team never gets this tool.

    Adds the payment to payments (dated the shop's date, with approved_by), takes the amount
    out of the cash account, marks an invoice paid or moves the lease's next_due on one
    month, and adds a "PAID" note to every open ticket linked to the bill (a ticket that was
    awaiting_approval goes back to in_progress). approved_by must be the full name of the
    person who approved it; a name that sounds like an agent is refused. Runs the same
    checks as propose_payment and never lets cash go negative.
    """
    approver = " ".join(approved_by.split())
    if not approver or set(re.findall(r"[a-z]+", approver.lower())) & AGENT_WORDS:
        raise ToolError("approved_by must be the name of the person who approved this payment, not an agent.")
    if READ_ONLY:
        raise ToolError("Dry run: the server is read-only, so no payment was recorded.")

    with _connect(write=True) as conn:
        check = _payment_check(conn, kind, ref_id, amount, account)
        if not check["ok"]:
            return {"paid": False, **check}
        today = check["shop_date"]
        payment_id = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, check["amount"], account, today, approver),
        ).lastrowid
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (check["balance_after"], today, account)
        )
        next_due = None
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        else:
            next_due = _add_month(date.fromisoformat(check["due_date"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))

        link = "invoice_id" if kind == "invoice" else "lease_id"
        tickets = [
            r["id"]
            for r in conn.execute(
                f"SELECT id FROM tickets WHERE {link} = ? "
                f"AND status NOT IN ({','.join('?' * len(CLOSED_STATUSES))})",
                (ref_id, *CLOSED_STATUSES),
            )
        ]
        note = (
            f"PAID ${check['amount']:,.2f} to {check['payee']} for {kind} {ref_id} from {account}, "
            f"approved by {approver} (payment {payment_id})."
        )
        for ticket_id in tickets:
            _ticket_note(conn, ticket_id, approver, note)
        # A ticket that was only waiting on this approval goes back to the team.
        conn.execute(
            f"UPDATE tickets SET status = 'in_progress' WHERE {link} = ? AND status = 'awaiting_approval'",
            (ref_id,),
        )
    return {
        "paid": True,
        "payment_id": payment_id,
        "kind": kind,
        "ref_id": ref_id,
        "payee": check["payee"],
        "amount": check["amount"],
        "account": account,
        "paid_at": today,
        "approved_by": approver,
        "balance_after": check["balance_after"],
        "below_cash_buffer": check["below_cash_buffer"],
        "lease_next_due": next_due,
        "tickets_noted": tickets,
    }


# --- Purchase orders --------------------------------------------------------------------
# A purchase order buys new stock from a vendor. The original database has no table for
# them, so purchase_orders is created in the working copy the first time one is proposed.

PO_TABLE = """CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    reason TEXT,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    expected_arrival TEXT
)"""


def _has_po_table(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'purchase_orders'"
    ).fetchone() is not None


def _purchase_check(conn: sqlite3.Connection, vendor_id: int, sku: str, size: str, qty: int,
                    account: str = "checking") -> dict:
    """What buying this stock would cost and do, and every reason it can't be bought now."""
    today = _shop_today(conn)
    vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
    if vendor is None:
        return {"ok": False, "problems": [f"No vendor with id {vendor_id}."]}
    price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if price is None:
        return {"ok": False, "problems": [f"No price for {sku}, so its cost is unknown."]}
    problems: list[str] = []
    if qty < 1:
        problems.append("qty must be at least 1.")
    if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
        problems.append(f"{sku} isn't a product the shop stocks in size {size}.")
    unpaid = _unpaid_invoices(conn, vendor_id)
    if unpaid:
        ids = ", ".join(str(i["id"]) for i in unpaid)
        problems.append(f"{vendor['name']} has unpaid invoice {ids} and ships nothing new until it is paid. Pay it first.")
    amount = _money(price["unit_cost"] * qty)
    cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    balance = cash["balance"] if cash else None
    after = _money(balance - amount) if cash else None
    if cash is None:
        problems.append(f"No cash account named '{account}'.")
    elif after < 0:
        problems.append(f"Not enough cash: {account} has ${balance:,.2f} and this costs ${amount:,.2f}.")
    return {
        "ok": not problems,
        "problems": problems,
        "vendor_id": vendor_id,
        "vendor": vendor["name"],
        "lead_days": vendor["lead_days"],
        "sku": sku,
        "size": size,
        "qty": qty,
        "unit_cost": price["unit_cost"],
        "amount": amount,
        "account": account,
        "balance_before": balance,
        "balance_after": after,
        "below_cash_buffer": after is not None and after < CASH_BUFFER,
        "cash_buffer": CASH_BUFFER,
        "expected_arrival": (today + timedelta(days=vendor["lead_days"])).isoformat(),
        "shop_date": today.isoformat(),
    }


@mcp.tool
def propose_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int,
                           proposed_by: str, reason: str) -> dict:
    """Propose buying new stock from a vendor, for a human manager to approve. Moves no money.

    The cost is qty times the shop's unit_cost for the sku (pricing table). Checks that the
    vendor exists and has no unpaid invoice (a vendor ships nothing new until it is paid),
    that the shop stocks the sku in that size, and that checking can cover it. Shows the
    balance after (below_cash_buffer flags a balance under the buffer). If every check
    passes, saves the purchase order as "proposed", adds a "PURCHASE PROPOSED" note to the
    ticket and sets it to awaiting_approval; otherwise proposed = false with the problems.
    Only propose stock a customer has asked for or a person has requested.
    """
    sku, size = sku.strip().upper(), size.strip().upper()
    proposed_by, reason = " ".join(proposed_by.split()), " ".join(reason.split())[:200]
    if not proposed_by:
        raise ToolError("proposed_by is required.")
    with _connect(write=not READ_ONLY) as conn:
        ticket = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return {"found": False, "ticket_id": ticket_id, "message": f"No ticket with id {ticket_id}."}
        if ticket["status"] in CLOSED_STATUSES:
            return {"proposed": False, "ticket_id": ticket_id, "problems": [f"Ticket {ticket_id} is {ticket['status']}."]}
        check = _purchase_check(conn, vendor_id, sku, size, qty)
        if check["ok"] and _has_po_table(conn) and conn.execute(
            "SELECT 1 FROM purchase_orders WHERE ticket_id = ? AND vendor_id = ? AND sku = ? AND size = ? AND status = 'proposed'",
            (ticket_id, vendor_id, sku, size),
        ).fetchone():
            check["problems"].append("A purchase order for this stock is already waiting for a person.")
            check["ok"] = False
        if not check["ok"]:
            return {"proposed": False, "ticket_id": ticket_id, **check}

        def note(po_id: object) -> str:
            return (
                f"PURCHASE PROPOSED: PO {po_id}, {qty} x {sku} size {size} from {check['vendor']} at "
                f"${check['unit_cost']:,.2f} = ${check['amount']:,.2f}, leaving ${check['balance_after']:,.2f}"
                f"{' (BELOW the cash buffer)' if check['below_cash_buffer'] else ''}. "
                f"Reason: {reason or 'not given'}. Awaiting human approval."
            )

        if READ_ONLY:
            return {"proposed": False, "dry_run": True, "ticket_id": ticket_id, "would_add_note": note("(new)"), **check}
        conn.execute(PO_TABLE)
        po_id = conn.execute(
            "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, amount, status, "
            "proposed_by, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?)",
            (ticket_id, vendor_id, sku, size, qty, check["unit_cost"], check["amount"], proposed_by, reason,
             check["shop_date"]),
        ).lastrowid
        line = _ticket_note(conn, ticket_id, proposed_by, note(po_id), "awaiting_approval")
    return {"proposed": True, "requires_human_approval": True, "po_id": po_id, "ticket_id": ticket_id,
            "ticket_note": line, **check}


@mcp.tool
def list_purchase_orders(status: str | None = None) -> dict:
    """List purchase orders (all, or only "proposed" / "approved"), newest first.

    A proposed order also carries the checks record_purchase will run now (ok, problems,
    balance_after, below_cash_buffer), so a person sees them before approving.
    """
    with _connect() as conn:
        if not _has_po_table(conn):
            return {"count": 0, "purchase_orders": []}
        rows = conn.execute(
            "SELECT * FROM purchase_orders" + (" WHERE status = ?" if status else "") + " ORDER BY id DESC",
            (status,) if status else (),
        ).fetchall()
        orders = []
        for r in rows:
            order = dict(r)
            if r["status"] == "proposed":
                check = _purchase_check(conn, r["vendor_id"], r["sku"], r["size"], r["qty"])
                order.update({k: check.get(k) for k in ("ok", "problems", "balance_before", "balance_after",
                                                         "below_cash_buffer", "cash_buffer", "vendor", "expected_arrival")})
            orders.append(order)
    return {"count": len(orders), "purchase_orders": orders}


@mcp.tool
def record_purchase(po_id: int, approved_by: str, account: str = "checking") -> dict:
    """HUMAN MANAGER ONLY: approve and pay a proposed purchase order. The agent team never gets this tool.

    Re-runs the purchase checks (vendor has no unpaid invoice, enough cash, never below
    zero), then adds the payment to payments (kind "purchase", ref_id = po_id, dated the
    shop's date, with approved_by), takes the amount out of the cash account, marks the
    order approved with its expected arrival, and adds a "PURCHASED" note to its ticket
    (a ticket that was awaiting_approval goes back to in_progress). Stock is added to
    inventory when it arrives, not now. approved_by must be a person's full name.
    """
    approver = " ".join(approved_by.split())
    if not approver or set(re.findall(r"[a-z]+", approver.lower())) & AGENT_WORDS:
        raise ToolError("approved_by must be the name of the person who approved this purchase, not an agent.")
    if READ_ONLY:
        raise ToolError("Dry run: the server is read-only, so no purchase was recorded.")
    with _connect(write=True) as conn:
        order = conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (po_id,)).fetchone() if _has_po_table(conn) else None
        if order is None:
            return {"purchased": False, "problems": [f"No purchase order with id {po_id}."]}
        if order["status"] != "proposed":
            return {"purchased": False, "problems": [f"Purchase order {po_id} is already {order['status']}."]}
        check = _purchase_check(conn, order["vendor_id"], order["sku"], order["size"], order["qty"], account)
        if not check["ok"]:
            return {"purchased": False, "po_id": po_id, **check}
        today = check["shop_date"]
        payment_id = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES ('purchase', ?, ?, ?, ?, ?)",
            (po_id, check["amount"], account, today, approver),
        ).lastrowid
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (check["balance_after"], today, account))
        conn.execute(
            "UPDATE purchase_orders SET status = 'approved', approved_by = ?, approved_at = ?, expected_arrival = ? WHERE id = ?",
            (approver, today, check["expected_arrival"], po_id),
        )
        if order["ticket_id"] is not None:
            _ticket_note(
                conn, order["ticket_id"], approver,
                f"PURCHASED: PO {po_id}, {order['qty']} x {order['sku']} size {order['size']} from {check['vendor']} for "
                f"${check['amount']:,.2f} from {account}, approved by {approver} (payment {payment_id}). "
                f"Expected {check['expected_arrival']} at the earliest.",
            )
            conn.execute(
                "UPDATE tickets SET status = 'in_progress' WHERE id = ? AND status = 'awaiting_approval'",
                (order["ticket_id"],),
            )
    return {
        "purchased": True,
        "po_id": po_id,
        "payment_id": payment_id,
        "ticket_id": order["ticket_id"],
        "vendor": check["vendor"],
        "sku": order["sku"],
        "size": order["size"],
        "qty": order["qty"],
        "amount": check["amount"],
        "account": account,
        "approved_by": approver,
        "balance_after": check["balance_after"],
        "below_cash_buffer": check["below_cash_buffer"],
        "expected_arrival": check["expected_arrival"],
    }


if __name__ == "__main__":
    mcp.run(show_banner=False)
