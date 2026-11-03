"""Customer Service: the shop's voice; drafts every message to customers and requesters."""

from models import AgentSpec

SPEC = AgentSpec(
    role="customer_service",
    title="Customer Service",
    prompt_file="customer_service.md",
    handles="drafting replies to customers, student groups and other requesters, using facts "
    "the team has confirmed",
    mcp_tools=("get_ticket", "check_stock", "add_ticket_note"),
)
