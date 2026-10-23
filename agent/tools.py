"""BugTriage AI tools: look up known bugs and format a new bug report for triage.

The agent has two tools:
- `lookup_bug`: retrieves a known bug by ID from the synthetic dataset in agent/data/bugs.json.
- `format_bug_report`: accepts the user's bug fields and returns the formatted state string
  that is sent to Strands Decider 2B.  The agent calls this before the policy check.
"""

from __future__ import annotations

import json
from pathlib import Path

from strands import tool

_DATA_FILE = Path(__file__).parent / "data" / "bugs.json"


def _load_bugs() -> list[dict]:
    if _DATA_FILE.exists():
        return json.loads(_DATA_FILE.read_text())
    return []


@tool
def lookup_bug(bug_id: str) -> dict:
    """Look up a known bug report by its ID (e.g. BUG-001) from the synthetic dataset."""
    bugs = _load_bugs()
    bug_id = bug_id.strip().upper()
    for b in bugs:
        if b.get("id", "").upper() == bug_id:
            return b
    return {"error": f"No bug found with ID {bug_id}. Available IDs: {[b['id'] for b in bugs]}"}


@tool
def list_bugs() -> list:
    """List all known bug IDs and their titles from the synthetic dataset."""
    bugs = _load_bugs()
    return [{"id": b["id"], "title": b["title"], "severity": b.get("severity", "")} for b in bugs]


@tool
def format_bug_report(
    title: str,
    description: str,
    error_message: str = "",
    users_affected: str = "",
    severity: str = "",
    steps_to_reproduce: str = "",
    workaround: str = "",
) -> str:
    """Format a bug report into the structured state text used by Strands Decider 2B for triage.

    Call this tool when the user provides bug details. The returned text is the exact input
    the decider evaluates. Required: title and description. Other fields improve triage accuracy.
    """
    from .decision import format_state

    return format_state(
        title=title,
        description=description,
        error_message=error_message,
        users_affected=users_affected,
        severity=severity,
        steps_to_reproduce=steps_to_reproduce,
        workaround=workaround,
    )


TOOLS = [lookup_bug, list_bugs, format_bug_report]
