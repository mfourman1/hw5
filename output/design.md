# Campus Customs Operations Desk: design

The dashboard (`frontend/`, React + Vite + TypeScript) is the desk a Campus Customs manager sits at. It lets them hand tickets to the agent team, watch the team work, and approve anything that moves money. It talks to the FastAPI backend at `http://localhost:8000`.

Run it:
1. From `backend/`: `uvicorn main:app --reload --port 8000`, with the project's `.venv` active.
2. From `frontend/`: `npm run dev`. This opens `http://localhost:5173`.

## The idea

It should feel like a **real shop desk**, not a log viewer. The page is a warm paper surface under a Yale-navy header, the colors of a New Haven shop rather than a generic admin theme. Everything on it answers one of three questions a manager has:

1. **What's waiting on me?** The ticket queue and the "Your move" panel.
2. **What is the team doing right now?** The team floor and the live feed.
3. **What did it cost?** The checking balance, always in the header.

## Layout

| Area | Where | What it shows | Why |
|---|---|---|---|
| **Header** | Top, always visible (sticky) | Shop name, the shop's date (2026-08-31), the **checking balance** card, and **Reset desk** | Cash and "today" are the two facts every decision depends on, so they never scroll away |
| **Ticket queue** | Left rail | The three tickets **sorted by deadline**: overdue on top, then the ones due soonest, then later ones, then tickets with no deadline. Each card shows its **due date** ("Due Fri, Aug 28 · 3 days late", "Reply by Tue, Sep 1, 4:55 PM · tomorrow") in red, amber or blue by how close it is, and where it **came from** when that's recorded. Resolved tickets sink to the bottom. A progress bar reads "1/3 resolved". | You can see the whole week's deadlines at a glance without opening a ticket, which matters most when volume is heavy |
| **Ticket header** | Top of the workspace | Ticket number, type, urgency ("Overdue · 3 days late"), the requester's own words in quotes, and the **Send to the team** button with a "Practice run" switch | One obvious action per ticket. The practice switch makes it safe to try things. |
| **The team** | Below the header | An org chart: the Boss on top, wires down to the four specialists | You can *see* delegation: a specialist's wire lights up in its color when it is called |
| **Live feed** | Left of the work area | Every step as it happens: hand-offs, tool calls with their results, each agent's closing words. Each step is **timed** from the start of the run (+0:42), and long waits are flagged. | It is the story of the run, readable while it unfolds, and it shows exactly where a run hangs |
| **Your move** | Right of the work area | The one thing the person needs to do now: wait, approve a payment, sign off, or nothing (resolved) | The board never makes you hunt for the button that matters |
| **Draft reply** | Under "Your move" | Customer Service's draft as a letter, with a Copy button | Drafts are for a person to send, so the page shows them as a letter, not a log line |
| **What each agent did** | Bottom | One card per agent: its status, its summary, and the notes or proposals it made. Agents that weren't needed show as faded "Not needed" cards. | A short after-action report. The faded cards make "not every specialist on every ticket" visible. |

## Changes I asked for after the first draft

1. **Step times in the live feed.**
   - Every step has a time column showing how long into the run it happened (+0:12, +0:43). Hovering shows the clock time and the gap from the step before.
   - A gap of 5 seconds or more is labeled ("12s wait"). From 15 seconds it turns **amber**, and from 45 seconds **red**, with a tinted edge on the step.
   - While a run is live, the last line counts up the seconds since the previous step and changes its wording as it waits longer:
     - *Waiting for the next step…*
     - *Still on the same step (20s)…*
     - *No new step for 50s. This one is taking unusually long.*

   **Why:** you can see where the system hangs, and whether it is the model thinking, a tool, or a hand-off.
2. **Due dates on the queue.** Every queue card shows its deadline in words, so you don't have to click a ticket to see when it is due.
   - The date says what kind of deadline it is: "Due" for a bill or rent, "Reply by" with a time for an inquiry.
   - It also says how far off it is: "3 days late", "tomorrow", "in 2 days".
   - The color matches the urgency: red for overdue, amber for due soon, blue for later.

   **Why:** with heavy volume you need to see the deadlines across the whole queue at once.
3. **Where a ticket came from.** Each ticket can be flagged **Online**, **In person** or **Called in**. The ticket header has a "Came in" picker, and the queue card shows a small tag once it's set. Today's three tickets are left blank ("Not recorded") because we don't know their source.
   - It is stored in a new `source` column on `tickets`, set through the MCP tool `set_ticket_source` and the route `POST /api/tickets/{id}/source`.

   **Why:** future tickets can be flagged as they arrive, so the shop can see which channel brings in the work.
4. **The queue ranks by deadline.** Overdue first, then close to due, then farther out, then no deadline. Inquiries sort by their exact reply-by time. Today the order is #101 (3 days late), #103 (reply by tomorrow), then #102 (rent in 2 days).
5. **Inquiries get a 24-hour reply deadline.** Ticket 103 is an inquiry, not an order, so the board calls it a "Price inquiry".
   - Every inquiry (price request or question) now has a deadline 24 hours after it came in. For ticket 103 that's Tue, Sep 1, 4:55 PM.
   - `get_ticket_urgency` returns it as `reply_by`, the agents follow it (shop rule 13), and the queue sorts by it.

   **Why:** a slow answer can lose the sale.

## How the agents read differently

Each agent has its **own color, its own icon, and its own voice**, so you can tell who is talking without reading the name.

| Agent | Color | Icon | Voice in the feed | Why |
|---|---|---|---|---|
| **Boss** | Yale navy | Compass (sets direction) | **Memo**: its closing words are set in a serif, like a manager's note | The Boss decides, so it reads with authority |
| **Inventory** | Green | Box | **Count**: a light green wash, with tool chips like "check stock CC-TEE-WHITE · S → 0 on hand — out of stock" | Stock is about numbers on a shelf, and green means "in stock" |
| **Accounting** | Amber / gold | Ledger with a $ | **Ledger**: closing words sit on faint ruled ledger lines, with even-width numbers | Money should look like a ledger, and figures line up |
| **Facilities** | Purple | Storefront | **Inspection tag**: a dashed border | Facilities checks the lease, like an inspector's tag on a building |
| **Customer Service** | Rose | Speech bubble | **Letter**: rounded speech-bubble corners and italic text, and its draft shows as a letter | It is the only voice that speaks to people outside the shop |

On the team floor, each agent's desk card has a status light:
- grey **Ready**
- pulsing in its own color: **Working**
- gold: **Waiting on a teammate**
- green: **Done**
- orange: **Blocked / Needs approval**

The card also shows its latest line and the tool it is using right now. If an agent is asked twice, it says "asked 2×".

In the feed, hand-offs are indented by depth (Boss → Accounting → Facilities steps right), so the chain of who asked whom reads like an outline.

## How resolved tickets show up

- **In the queue:** a green **RESOLVED** rubber stamp lands on the card (with a short stamp animation). The card fades, gets a green edge, and drops to the bottom of the queue. The progress bar fills in green.
- **On the ticket:** the header's top edge turns green, and "Your move" becomes a green check with the resolution note, for example "Resolved after Mitchell Fourman approved the $2,400.00 payment to Elm City Properties."
- **A toast** says what happened when a run finishes or a payment resolves a ticket.

When a ticket is resolved, which the backend decides:
- **Run finishes with nothing waiting:** the Boss reports "done" and no payment is waiting, so the ticket is resolved as soon as the run finishes.
- **A payment is waiting:** the ticket shows **Needs your approval**, and is resolved when the person approves the last payment.
- **Some other sign-off is needed, or the team got blocked:** the ticket shows **Needs your sign-off** or **Needs attention**, and a person can sign off, with a note, or run the team again.
- **Practice runs never resolve anything.**

## How cash shows up

- **The checking balance is always in the header.** A thin meter under it shows the balance against the starting amount, with a gold line at the **$500 cash buffer**. The card turns amber if checking drops below the buffer.
- **When a payment is approved, the number visibly drains.** It counts down from the old balance to the new one over about a second, and a red **−$2,400.00** tag pops up next to it. The drop is meant to be felt, because a person just moved real money.
- **Payments and purchase orders use the same card.** A purchase order shows the items (e.g. "PO 1: 12 × CC-HOOD-NAVY size M at $22.00") and its expected arrival.
- **The approval card shows the effect before you click:** "Checking $3,400.00 → **$1,000.00**", with a warning if it would go below the buffer. The button names the exact amount ("Approve & pay $2,400.00"), so nobody approves a number they didn't read.
- **Clicking the balance opens a cash log:** the starting balance after the last reset, each approved payment (what, to whom, which ticket, who approved it), and the balance now. It is the itemized cash story the Cash tab in Problem 9 needs.

## Choices that make it a place people want to work

- **One next step at a time.** "Your move" changes with the ticket: *Ready when you are*, then *The team is on it · 0:42* (with a running clock), then *Your approval is needed*, then *Resolved*. You always know whether you are waiting or acting.
- **The approver's name is remembered** in the browser, so approving is two clicks, but it is always a named person. The page also refuses agent names.
- **Watching is satisfying.** Desk lights pulse, wires light up as work is handed down, new feed lines slide in, and the feed follows the newest line unless you scroll up to read.
- **Tool calls are written in plain words** ("read lease · lease 1 → $2,400.00 to Elm City Properties, due 2026-09-02"), not raw JSON. The feed reads like the team describing its work.
- **Honest about practice.** Practice runs are tagged everywhere ("practice run · nothing saved").
- **Calm when something is wrong.** If the backend isn't running, a red banner says exactly which command starts it, and the page reconnects on its own.
- **Respects reduced-motion settings.** All animation turns off for people who ask their system for less motion.

## Files

| File | What it holds |
|---|---|
| `frontend/src/App.tsx` | Page state, polling (every 2 s while the team works, 15 s otherwise), and the actions: run, approve, sign off, reset |
| `frontend/src/api.ts` | Types and calls for every backend route (`VITE_API_URL` in `frontend/.env`) |
| `frontend/src/agents.tsx` | Each agent's title, role line, voice and icon |
| `frontend/src/components/TopBar.tsx` | Brand, shop date, the cash card with its meter, drain animation and cash log, and Reset |
| `frontend/src/components/TicketQueue.tsx` | The queue, the urgency chips and the RESOLVED stamp |
| `frontend/src/components/TeamFloor.tsx` | The org-chart floor and each desk's live state |
| `frontend/src/components/LiveFeed.tsx` | The feed: hand-offs, tool chips with results, and agent voices |
| `frontend/src/components/TicketView.tsx` | The ticket header, the "Your move" panel and the payment approval card |
| `frontend/src/components/RunSummary.tsx` | "What each agent did", the draft letter, and the Boss's approval list |
| `frontend/src/styles.css` | The whole look: paper desk, agent colors and voices, stamp, meter, motion |
