"""Accounting: prices and quotes, vendor invoices, cash, and payment proposals (never payments)."""

from models import AgentSpec

SPEC = AgentSpec(
    role="accounting",
    title="Accounting",
    prompt_file="accounting.md",
    handles="prices, bulk quotes and discounts, vendor invoices, cash on hand, and proposing "
    "payments for a person to approve",
    mcp_tools=(
        "get_ticket",
        "get_pricing",
        "quote_bulk_price",
        "get_invoice",
        "get_cash_balance",
        "propose_payment",
        "add_ticket_note",
    ),
)
