"""Facilities: the Chapel Street shop space, the lease and landlord, and deliveries."""

from models import AgentSpec

SPEC = AgentSpec(
    role="facilities",
    title="Facilities",
    prompt_file="facilities.md",
    handles="the shop's lease and landlord (checking rent notices against the lease), the "
    "building, and local courier deliveries",
    mcp_tools=("get_ticket", "get_ticket_urgency", "get_lease", "get_vendor_lead_time", "add_ticket_note"),
)
