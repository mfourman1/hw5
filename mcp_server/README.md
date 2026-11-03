# Campus Customs MCP server

**What it is for:** This FastMCP server (`server.py`, server name `campus-customs`) is the shared toolbox for Campus Customs.
- **Who uses it:** the five agents (Boss, Inventory, Accounting, Facilities, Customer Service) and the vibe coder, through `.mcp.json`. It has 20 tools.
- **What the tools do:** look up the shop's real stock, prices, tickets, bills, rent and cash. They also record the team's work on tickets.
- **No made-up data:** if something is not in the database, a tool returns `found: false`.

**Database:** `../data/campus_customs_new.db`, the working copy of the shop database. The original `data/campus_customs.db` is never used. Read tools open the file read-only. The shop's date is `desk.date_today`, not the computer's clock.

## Tools

| Tool | Tables | What it returns or does |
|---|---|---|
| `check_stock(sku, size)` | `inventory` | Units on hand and aisle for one product in one size, plus the count for every size |
| `get_lease(lease_id)` | `leases`, `desk` | Landlord, monthly rent, next due date, and days until rent is due |
| `get_pricing(sku)` | `pricing` | List price, unit cost, and margin per unit |
| `get_ticket_urgency(ticket_id)` | `tickets`, `invoices`, `leases`, `desk` | The ticket's earliest deadline: a linked due date, or for inquiries a 24-hour reply-by (`reply_by`). Returns days left and an urgency label: overdue, due_soon (0–3 days), upcoming, no_deadline, or not_open. |
| `get_vendor_lead_time(vendor_id, specialty)` | `vendors`, `invoices`, `desk` | A vendor's lead days and earliest arrival if ordered on the shop's date. A vendor with an unpaid invoice is `on_hold`: it ships nothing new, so there is no date until the invoice is paid. |
| `list_open_tickets()` | `tickets`, `desk` | Every ticket that is not resolved or closed, oldest first |
| `list_tickets()` | `tickets`, `desk` | Every ticket, resolved ones too, with `open` true or false and its `source` (used by the backend's ticket board) |
| `set_ticket_source(ticket_id, source)` | `tickets` | **Writes.** Records where a ticket came from: online, in_person or phone; null clears it. Adds the `source` column to the working database the first time it's used. **Desk only.** |
| `get_ticket(ticket_id)` | `tickets` | One ticket in full: request, linked product, lease or invoice, status, notes |
| `add_ticket_note(ticket_id, author, note, new_status)` | `tickets` | **Writes.** Adds a dated, signed note (500 characters max) and can change the status. Notes are never edited or removed. |
| `get_invoice(invoice_id)` | `invoices`, `vendors`, `payments`, `desk` | A vendor bill: amount, due date, overdue or not, the vendor, payments made, amount outstanding |
| `get_cash_balance()` | `cash_accounts`, `desk` | Cash in each account and the $500 cash buffer |
| `quote_bulk_price(sku, qty, discount_pct)` | `pricing` | Unit and total price at a discount, the shop's cost and margin, and a decision: allowed, needs_human_approval or not_allowed |
| `propose_payment(ticket_id, kind, ref_id, amount, proposed_by, reason)` | `tickets`, `invoices`, `vendors`, `leases`, `cash_accounts`, `desk` | **Writes a note only.** Checks a bill, then adds a "PAYMENT PROPOSED" note and sets the ticket to awaiting_approval. Moves no money. |
| `list_payment_proposals()` | `tickets`, `invoices`, `vendors`, `leases`, `cash_accounts`, `desk` | Proposed payments that are still unpaid, each with the checks `record_payment` will run (used by the backend's approve routes) |
| `record_payment(kind, ref_id, amount, approved_by, account)` | `payments`, `cash_accounts`, `invoices` or `leases`, `tickets`, `desk` | **Writes. Human manager only.** No agent is given this tool. Pays an approved bill and refuses an approver that names an agent. The backend calls it from `POST /api/payments/approve`. **Desk only.** |
| `propose_purchase_order(ticket_id, vendor_id, sku, size, qty, proposed_by, reason)` | `vendors`, `pricing`, `inventory`, `invoices`, `cash_accounts`, `purchase_orders`, `tickets`, `desk` | **Writes a proposal only.** Proposes buying stock at unit cost. Refuses a vendor on hold or more than checking holds. Adds a "PURCHASE PROPOSED" note and sets the ticket to awaiting_approval. Moves no money. |
| `list_purchase_orders(status)` | `purchase_orders` | Proposed and approved purchase orders, with what approval would do to cash |
| `record_purchase(po_id, approved_by, account)` | `purchase_orders`, `payments`, `cash_accounts`, `tickets`, `desk` | **Writes. Human manager only.** Approves and pays a purchase order (`payments.kind = 'purchase'`) after re-checking the vendor hold and cash. The backend calls it from `POST /api/payments/approve`. **Desk only.** |
| `reset_working_copy(confirm)` | all tables | **Writes. Desk only.** Copies the original `data/campus_customs.db` over the working copy for a fresh run. The backend calls it from `POST /api/reset`. |

The shop rules the tools enforce (discount limits, the cash buffer, the vendor hold) are constants at the top of `server.py`. They must match `backend/prompts/shop_rules.md`.

## Setup

```bash
pip install -r requirements.txt
python server.py
```

`python server.py` serves the tools over stdio for an MCP client. The project's root `requirements.txt` installs the server too, so one environment runs everything. `.mcp.json` at the project root starts it as `python mcp_server/server.py`. The agent backend reads the same file and runs the server with its own Python.

Optional environment variables:
- `CAMPUS_CUSTOMS_READ_ONLY=1`: dry run. Write tools report what they would do and change nothing. The backend's `--dry-run` sets this.
- `CAMPUS_CUSTOMS_DB`: point the server at another database file, for tests.
- `CAMPUS_CUSTOMS_DESK=1`: this connection is the desk. The backend sets it only for its own connection, which serves the dashboard. Without it, `record_payment`, `record_purchase`, `set_ticket_source` and `reset_working_copy` refuse, so the agents and a vibe coder can't pay, buy or reset.
