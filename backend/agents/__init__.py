"""The five Campus Customs agents. Each file defines one agent's SPEC: its prompt file in
backend/prompts/, the MCP tools it may call, and what teammates should ask it for.
team.py builds a PydanticAI agent from each SPEC and gives every agent an ask_<role> tool
for each of the other four (full connectivity)."""

from agents.accounting import SPEC as ACCOUNTING
from agents.boss import SPEC as BOSS
from agents.customer_service import SPEC as CUSTOMER_SERVICE
from agents.facilities import SPEC as FACILITIES
from agents.inventory import SPEC as INVENTORY
from models import AgentSpec, RoleName

SPECS: dict[RoleName, AgentSpec] = {
    spec.role: spec for spec in (BOSS, INVENTORY, ACCOUNTING, FACILITIES, CUSTOMER_SERVICE)
}
