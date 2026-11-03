# Homework 5: Campus Customs Multi-Agent Operations

A five-agent team (**Boss, Inventory, Accounting, Facilities, Customer Service**) works Campus Customs' ticket queue.

- **Agents:** PydanticAI agents on **gpt-6-luna** (through Portkey).
- **Data:** every shop fact comes from one **MCP server** over the shop's SQLite database.
- **Backend:** a FastAPI backend runs the team.
- **Dashboard:** a React desk lets a person watch the agents, approve payments and see the checking balance.

The full write-up is [`output/harness.md`](output/harness.md), covering tables, MCP tools, agents, shop rules, routes, dashboard and safety. The ticket plans, the real results, the cash and the reflection are in [`output/desk_tickets.html`](output/desk_tickets.html), which you can double-click to open.

## Layout

```
hw5/
├── AI_prompts.md            my prompts to the vibe coder, problem by problem
├── requirements.txt         one Python environment for everything
├── .env.example             copy to .env and add PORTKEY_API_KEY
├── .mcp.json                the MCP server for the vibe coder (and the backend reads it too)
├── data/
│   ├── campus_customs.db       the original database (never changed)
│   └── campus_customs_new.db   the working copy the app reads and writes
├── mcp_server/              server.py (the campus-customs FastMCP server) and README.md
├── backend/                 main.py (FastAPI), team.py (agent loop), models.py, config.py,
│   │                        audit.py, run.py, agents/ (one file per agent)
│   └── prompts/             shop_rules.md + boss.md, inventory.md, accounting.md,
│                            facilities.md, customer_service.md
├── frontend/                the React + Vite + TypeScript dashboard
└── output/                  harness.md, mcp_smoke.json, desk_tickets.html, design.md,
                             resolved_tickets.json, resolved_board.html (+ images),
                             audit_trail.json, github_url.txt
```

## Setup (once)

You need Python 3.11+ and Node.js 20+.

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Then copy `.env.example` to `.env` and put in your `PORTKEY_API_KEY`. Every agent uses `gpt-6-luna` through Portkey.

## Running it

### 1. Start from a clean database (when you need a fresh run)

`data/campus_customs_new.db` is the working copy. It currently holds the end of my Problem 9 run: all three tickets resolved and checking at $160. To start over, copy the original over it:

```bash
copy data\campus_customs.db data\campus_customs_new.db     # macOS/Linux: cp data/campus_customs.db data/campus_customs_new.db
```

While the app is running, you can do the same with the **Reset desk** button on the board, or `POST /api/reset` with `{"confirm": true}`. Either way the audit trail is kept.

### 2. The MCP server

The backend starts the `campus-customs` MCP server by itself, the way `.mcp.json` says (`python mcp_server/server.py`, with the backend's own Python), so you don't need a separate terminal.

To run it on its own, for example for the vibe coder or to try the tools:

```bash
python mcp_server/server.py
```

With the environment active, Claude Code picks it up from `.mcp.json` when opened in this folder. The tools are listed in [`mcp_server/README.md`](mcp_server/README.md).

### 3. Start the FastAPI backend

In terminal 1, with `.venv` active:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

It runs at http://localhost:8000, with interactive docs at http://localhost:8000/docs.

### 4. Start the React board

In terminal 2:

```bash
cd frontend
npm run dev
```

This opens the desk at http://localhost:5173. It talks to the backend at http://localhost:8000.

### 5. A full three-ticket run

1. **Reset the database first:** step 1, or **Reset desk** on the board. Checking goes back to **$3,400.00** and all three tickets reopen.
2. **Run each ticket:** click it in the queue, then **Send to the team**. Watch the team floor and the live feed.
3. **Approve payments:** when a ticket shows **Needs your approval**, type your name under "Approving as" and click **Approve & pay**. Purchase orders work the same way, with **Approve & buy**. That is the only thing that moves cash.
   - #102: $2,400 rent. Approve it first: rent goes first when cash is short.
   - #101: $840 for invoice 501.
4. **Watch it resolve:** a ticket is resolved when its run finishes with nothing waiting (#103), or when its last payment is approved (#101, #102).
5. **Expected ending balance:** $3,400 − $2,400 − $840 = **$160.00**, below the $500 buffer. The board warns about this before you approve.

The **Practice run** switch runs a ticket without saving anything. To run a task from the terminal instead of the board: `python backend/run.py [--agent NAME] [--dry-run] "task"`.

Every step of every run is appended to `output/audit_trail.json`.
