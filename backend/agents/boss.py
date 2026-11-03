"""Boss: runs the ticket queue, routes work to the specialists, and reports to the manager."""

from models import AgentSpec

SPEC = AgentSpec(
    role="boss",
    title="Boss",
    prompt_file="boss.md",
    handles="deciding priorities between tickets, settling disagreements between agents, "
    "and anything that needs a decision above one specialist",
    mcp_tools=("list_open_tickets", "get_ticket", "get_ticket_urgency", "add_ticket_note"),
)
