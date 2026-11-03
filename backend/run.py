"""Give a task to the Campus Customs agent team from a terminal.

Run with the project's Python (from the project folder, with .venv active):

    .venv/Scripts/python backend/run.py "Plan ticket 101"
    .venv/Scripts/python backend/run.py --agent inventory "How many size M navy hoodies are on hand?"
    .venv/Scripts/python backend/run.py --dry-run "Plan ticket 102"   # nothing is saved

The task goes to the Boss unless --agent names another agent. The result (the agent's
report, how the run ended, and the tokens used) is printed as JSON, and every step is
appended to output/audit_trail.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from models import ROLES
from team import Team


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a task through the Campus Customs agent team.")
    parser.add_argument("task", nargs="+", help="what you want done, in plain words")
    parser.add_argument("--agent", choices=ROLES, default="boss", help="which agent gets the task (default: boss)")
    parser.add_argument("--dry-run", action="store_true", help="MCP server read-only: write tools save nothing")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    result = asyncio.run(Team(dry_run=args.dry_run).run_task(" ".join(args.task), args.agent))
    print(json.dumps(result.model_dump(exclude_none=True), indent=2, ensure_ascii=False))
    return 0 if result.stop_reason == "final_answer" else 1


if __name__ == "__main__":
    raise SystemExit(main())
