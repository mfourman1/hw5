"""Inventory: what is on the shelf, shortfalls, and when restocks can arrive."""

from models import AgentSpec

SPEC = AgentSpec(
    role="inventory",
    title="Inventory",
    prompt_file="inventory.md",
    handles="stock on hand by product and size, shortfalls, whether a restock is really coming, "
    "and vendor lead times / earliest arrival dates",
    mcp_tools=("get_ticket", "check_stock", "get_vendor_lead_time", "get_invoice", "add_ticket_note"),
)
