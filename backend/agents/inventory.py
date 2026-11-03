"""Inventory: what is on the shelf, shortfalls, and when restocks can arrive."""

from models import AgentSpec

SPEC = AgentSpec(
    role="inventory",
    title="Inventory",
    prompt_file="inventory.md",
    handles="stock on hand by product and size, shortfalls, whether a restock is really coming, "
    "vendor lead times / earliest arrival dates, and which vendor can restock (and whether it is on hold)",
    mcp_tools=("get_ticket", "check_stock", "get_vendor_lead_time", "get_invoice", "list_purchase_orders", "add_ticket_note"),
)
