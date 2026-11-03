# AI Prompts — Homework 5: Campus Customs Multi-Agent Operations

Log of the prompts I typed to my vibe coder (Claude Code) for each problem, in my own words. Each follow-up is followed by one sentence on what was lacking after the previous prompt.

---

## Problem 1: Vibe coder prompts

**Prompt:**

> We are now going to do the homework assignment. For Problem 1, we are going to create AI_prompts.md in the same format that it was in for HW3 and HW4. It must include the problem number and title, at least one prompt that I typed, in my own words as much as possible, and one follow-up prompt if I needed one (including one sentence on what was lacking after the first)

**Follow-up:** None needed.

---

## Problem 2: Study the Campus Customs database

**Prompt:**

> For Problem 2, I want you to open data/campus_customs.db and give me a description of every table and its fields. Copy the original file to data/campus_customs_new.db . Later problems will update that working copy.
>
> There are three open tickets. Tell me how they link to the other tables.
>
> Start output/harness.md . For each table, list the fields and one short line on why that table matters for the agents. output/harness.md will grow in later problems

**Follow-up:**

> Yes, add them

*What was lacking:* The AI explained how the three open tickets link to the other tables only in chat, so I asked for that to be added to output/harness.md. (I sent this by clicking a quick-reply button in the coder.)

---

## Problem 3: Build the MCP server

**Prompt:**

> For Problem 3, we are going to build the MCP server. We are going to write an MCP server in mcp_server/ using FastMCP. It will talk to data/campus_customs_new.db. Do not connect or run it in this problem.
>
> Every agent in this homework will use the tools in this MCP server. Can you first recommend for me three tools that will be needed for tickets in this database?

**Follow-up:**

> Build these three. I want to also add a fourth tool that looks at the urgency of an order and a fifth that looks at the lead days of a vendor. Can you recommend how to do this?

*What was lacking:* The AI only recommended the three tools without building them, and nothing in its plan told the agents how urgent a ticket is or how long a vendor takes to deliver.

> Build both. In output/harness.md , list each MCP tool and for each tool include a table that reads which ticket it helps unlock and one sentence on why that tool is the right one for that ticket. For my additional tools that are unrelated, add a sentence that justifies why these may be useful in the future. Vague lines like "reads inventory" score low - tie the tool to the ticket.
>
> Also, add a short mcp_server/README.md file that explains what the MCP server is for, which database file it uses, and the tools that it has

*What was lacking:* The urgency and vendor lead-time tools were only recommended, not built, and neither output/harness.md nor a README described any of the MCP tools yet.

---

## Problem 4: Add the MCP server to vibe coder and test each tool

**Prompt:**

> Problem 4 will add the MCP server to the vibe coder and test each tool.
>
> Add the MCP server to this project so that I can call the tools. Save the connection JSON text in .mcp.json at the project root.
>
> Test each of the five MCP tools I have. Save the evidence in output/mcp_smoke.json . For every tool include the prompt that was asked, the tool name, and the tool output (which much match the values in data/campus_customs_new.db)

**Follow-up:**

> restart the session

*What was lacking:* The server and .mcp.json were set up, but the coder only loads MCP servers when a session starts, so it could not call the tools yet (and it could not restart the session itself, so I restarted the app).

> It's connected

*What was lacking:* After the restart, the five tools still had not been tested and output/mcp_smoke.json did not exist yet.

> Keep them. I reviewed each test prompt and understand how it functions. All functions appear appropriate

*What was lacking:* The AI had written the five per-tool test questions itself, so I reviewed them and confirmed they were right before keeping them.

---

## Problem 5: Build the agent team and grow the MCP tools

**Prompt:**

> Problem 5 has us build the agent team and grow the MCP tools
>
> We will build the agentic team for Campus Customs using PydanticAI: Boss, Inventory, Accounting, Facilities and Customer Service. Include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Make a table for me to understand how they will function.
>
> Put the agent prompts in backend/prompts/ . Male one file per agent. Put data types in backend/models.py and the agent files under backent/ . The layout can vary as long as the five roles are clear. Use the PORTKEY_API_KEY that I used in the other problems (link it here) and only use gpt-6-luna for every agent.
>
> Please propose for me some text for the shop rules that the agent needs and I will adjust and approve as needed. Please use more detailed prompts that cover all aspects of an agent's work and scope.
>
> Add any tools the agents need to the MCP server so they can work on the open tickets. Shop facts come from the MCP server over data/campus_customs_new.db . DO not invent a second shop-tools layer that bypasses MCP.
>
> The agents should be wired so that they append to output/audit_trail.json as they run. For each agent loop step, record enough to audit later. Append to this file - do not wipe it for each run.
>
> In output/harness.md , list each agent and each MCP tool (including the ones you add in this problem) along with which table the tool uses.
>
> Also add a short safety section. Propose to me guardrails that a real business would want when agents touch real customers and money, plus limits that keep token use in check. I will edit and add to these as needed.
>
> Update mcp_server/README.md so the tool list matches what you have now

**Follow-up:**

> Approve as written

*What was lacking:* The shop rules and the safety section were still marked as the AI's proposals waiting for my review, so I approved them.

---

## Problem 6: Plan the three tickets

**Prompt:**

> Problem 6 involves planning the three tickets.
>
> Before we wire the backend, we will write down the expected outcome of what the team will do on each open ticket.
>
> Build output/desk_tickets.html, a page I can double-click with one tab per ticket (101, 102, 103). Add empty Cash and Reflection tabs for later problems (leave them blank or with a short "coming later" note for now).
>
> On each ticket tab, fill an expected section only (leave room for an Actual section we will fill after the agents run).
>
> I want you to propose the following expected section for each ticket that includes the following information:
>
> 1. Who the boss should call first, and why
> 2. All the agent delegations you expect - not "Boss calls everyone"
> 3. Which MCP tools you expect that run to use
>
> Plans that send every specialist to every ticket score low. You will compare this plan to what actually happens when your agents resolve the three tickets

**Follow-up:**

> Approve as written

*What was lacking:* The expected plans for the three tickets were the AI's proposal, so I reviewed them and approved them before we compare them with the agents' actual runs.

---

## Problem 7: Backend routes

**Prompt:**

> Problem 7 looks at Backend routes.
>
> In backend/main.py, use FastAPI and add routes that do the following:
>
> 1. Return the three tickets and whether each is open or resolved
> 2. Take a ticket id and run your agent on that ticket
> 3. Return recent agent events - what each agent said and which tools they used - so the board can refresh
> 4. Approve a payment or purchase after a human clicks approve (agents only prepare the pay; this route is what actually changes cash)
> 5. Return the current checking balance from cash_accounts
> 6. Reset the database to the original values when you want to try a fresh run
>
> From the backent/ folder, start the server with:
> uvicorn main:app --reload --port 8000
>
> In output/harness.md, list each route in one line (what URL / what it does). Show me this in a table as well

**Follow-up:**

> Yes, fix it

*What was lacking:* Testing the run route showed Accounting asking Facilities to check the lease a second time, even though the Boss had already passed along Facilities' answer. That wasted a hand-off and didn't match my plan, so I asked for the Accounting prompt to be fixed.

> Leave it for Problem 9

*What was lacking:* After the fix, a test run had the Boss ask Customer Service to draft a reply to the landlord on ticket 102, which my plan didn't expect. I chose to leave the Boss as it is and compare this with my plan when the agents resolve the tickets in Problem 9.

---

## Problem 8: Agent dashboard

**Prompt:**

> Problem 8 will build the Agent Dashboard.
>
> Build the frontend dashboard in frontend/ with React + Vite + TypeScript. The page should call the routes that you built in Problem 7.
>
> At a minimum, the board should:
>
> 1. List all 3 tickets
> 2. Let you pick one ticket and start the agent team on it
> 3. Show each agent and what they are saying/doing while the ticket runs
> 4. Mark a ticket resolved when the run finishes
> 5. Show a short summary of what each agent did on that ticket
> 6. Let a human approve a pay or purchase when asked
> 7. Show the checking balance (it should drop after an approved pay)
>
> The dashboard should be intuitive and flow smoothly. I will likely make changes once the first draft is built.
>
> Tell the front end to talk to the backend at http://localhost:8000 . On the backend, allow the Vite page origin (usually http://localhost:5173) so the browser is allowed to call those routes.
>
> Start the board with:
> npm run dev
>
> This should open the React desk in my browser so I can pick the tickets and watch agents.
>
> Write output/design.md with details about the dashboard look (layout, how agents read differently, how resolved tickets and cash show up) and why. This will be modified to include further creative choices that I make once the first design is complete.

**Follow-up:**

> Yes, clarify it

*What was lacking:* Testing the board showed the Boss refusing to propose the rent on ticket 102 because the landlord's email gives no amount, and shop rule 4 said the amount must match. That would leave the rent ticket stuck, so I had rule 4 clarified: a detail the notice leaves out is decided by the lease, and only a detail that contradicts the lease is a mismatch.

> Yes, fix it

*What was lacking:* After the rule 4 fix, a test run on ticket 102 had Customer Service ask Facilities to check the lease again, even though the Boss had already given it the verified facts. That was a wasted hand-off. Fixing it also showed that Accounting would still re-check when the Boss didn't say which tool a fact came from. So now the Boss passes each fact on with its source, and Customer Service and Accounting use those facts instead of asking again.

> Run it so I can use it

*What was lacking:* The dashboard and backend were built and tested, but they weren't running for me to use.

> Additional components:
>
> 1. For the live feed, add times for each step so I can see where the system hangs if it does.
> 2. On the Ticket queue, put due date on the queue so I don't have to click on the ticket to see this. It will help me visualize heavy volume deadlines.
> 3. I want you to add an ability for me to tell where the ticket comes from (online submission vs. in person / called in ticket). This field can be left blank here since we don't know where these tickets came from, but I want future tickets to be able to be flagged in this way.
> 4. Ensure the ticket queue ranks tickets by deadline, with overdue on top, close to due after, than farther out deadlines after.
> 5. Ticket 103 is not an order, but an inquiry. These can still be time sensitive. Please attach a 24 hour turnover deadline to these types of requests so that the store avoids losing business by not responding fast enough

*What was lacking:* Using the first draft, I couldn't see where a run was slow and had to open each ticket to see its due date. There was also no way to record where a ticket came from. The queue wasn't strictly ordered by deadline, and inquiries like ticket 103 had no deadline at all, even though a slow reply can lose the sale.

> Yes, update it

*What was lacking:* After the 24-hour inquiry deadline was added, my Problem 6 plan for ticket 103 still said it had no deadline, so I had its Expected tab updated to show the reply-by time.

> show me what it looks like again

*What was lacking:* I wanted to see the updated desk_tickets.html page myself.

---

## Problem 9: Resolve the tickets

**Prompt:**

> Problem 9 will Resolve the tickets.
>
> Reset the working database data/campus_customs_new.db so you can start clean. Note the starting checking balance. Run all three tickets on the board until each is resolved.
>
> Then open output/desk_tickets.html . On each ticket tab, fill the Actual section from this run: which agents worked, what they delegated and which tools they used. Keep the Expected section so I can compare the two.
>
> On the Cash tab of the same output/desk_tickets.html, itemize the money using the following factors:
>
> 1. Starting checking balance (after the reset)
> 2. For each ticket, how cash changed when that ticket resolved, and why (which pay / purchase, dollar amount)
> 3. Ending checking balance - it must match cash_accounts in the working database.
>
> The cash math is important! An incorrect calculation will be graded down.
>
> Also save:
>
> 1. output/resolved_tickets.json for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals
> 2. output/resolved_board.html - a page you can double-click with a screenshot of your React board for each resolved ticket (101, 102, 103)
>
> Append real runs to output/audit_trail.json. Finish output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard and safety rules

**Follow-up:** (my answers to the AI's two questions after the first runs: ticket 101 had stalled, and payments were waiting for approval)

> Ticket 101: Clarify the rule, re-run
>
> Approvals: Approve for me

*What was lacking:* On the first run, ticket 101 came back blocked. Accounting wouldn't propose paying invoice 501 because it couldn't prove the linked invoice was the restock for this order. I chose to have the rule clarified (a ticket's linked invoice is its bill) and the ticket re-run. I also authorized the AI to click Approve in my name for the $2,400 rent and the $840 invoice, knowing checking would end at $160, below the $500 buffer.

---

## Problem 10: Reflection

**Prompt:**

> For Problem 10, we are doing the Reflection section.
>
> Open output/desk_tickets.html and fill the Reflection tab. For each one of the following questions, propose for me some thoughts and I will edit them and contribute my own vibe.
>
> 1. How would you evaluate the performance of the agents on each ticket and why?
> 2. For each ticket, how did Actual compare to the Expected plan you wrote earlier?
> 3. What would have been simpler as one agent with tools - and why?
> 4. Describe three new problems Campus Customs might face that this agent team could solve with the tools you built
> 5. Describe three new problems Campus Customs might face that this agent team could not solve with the tools you build, and explain the tools and agents you would need to solve them. Notably one immediate thought for this question is the idea of returns.
>
> Tie every answer to this app and the three tickets you ran - use the ticket tabs and Cash tab on the same page as your evidence.
>
> Generic AI essays without Campus Customs details will score low

**Follow-up:**

> Looks good as is

*What was lacking:* The Reflection answers were the AI's proposal, so I reviewed them and kept them as written.

---

## Problem 11: Submit to GitHub

**Prompt:**

> Problem 11 is to Submit to GitHub.
>
> Push the code to a public GitHub repository so graders can clone it.
>
> Please give me the repo url so I can submit it on Canvas. Also put this url into output/github_url.txt
>
> Do not push the real .env to the GitHub repo.
>
> Include both database files under data/ (the original and your working copy) so graders can run your app easily.
>
> This link is the expected file layout. https://zlisto.github.io/mgt_409_fa26/hw5/p11.html

*Note:* I linked the page only for its file-tree diagram (the expected layout). The task itself is in my own words above.

**Follow-up:** None needed.

---
