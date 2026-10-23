"""Tests for BugTriage AI decision wiring — all offline, using FakeDecider."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fakes import FakeDecider

ROOT = Path(__file__).resolve().parent.parent

# ── helpers ──────────────────────────────────────────────────────────────────


def make_policy(rule=None):
    from agent.decision import BugTriagePolicy

    return BugTriagePolicy(FakeDecider(rule))


def high_impact_complete_rule(state, name, q):
    """Simulates a complete, high-impact bug needing escalation."""
    return {
        "sufficient_info": 0.95,
        "high_impact": 0.92,
        "needs_escalation": 0.88,
        "action": "escalate",
    }.get(name, 0.9 if q["type"] == "noul" else next(iter(q["criteria"])))


def low_impact_complete_rule(state, name, q):
    """Simulates a complete, low-impact bug with a workaround."""
    return {
        "sufficient_info": 0.91,
        "high_impact": 0.08,
        "needs_escalation": 0.05,
        "action": "prioritize",
    }.get(name, 0.9 if q["type"] == "noul" else next(iter(q["criteria"])))


def missing_info_rule(state, name, q):
    """Simulates a bug report with missing critical fields."""
    return {
        "sufficient_info": 0.08,
        "high_impact": 0.20,
        "needs_escalation": 0.15,
        "action": "request_info",
    }.get(name, 0.9 if q["type"] == "noul" else next(iter(q["criteria"])))


def conflicting_signals_rule(state, name, q):
    """High severity claimed but very few users — uncertain escalation."""
    return {
        "sufficient_info": 0.45,   # borderline
        "high_impact": 0.35,       # conflicting
        "needs_escalation": 0.72,  # decider flags for human review
        "action": "escalate",
    }.get(name, 0.9 if q["type"] == "noul" else next(iter(q["criteria"])))


def unclear_error_rule(state, name, q):
    """Unclear error, no steps to reproduce — insufficient info."""
    return {
        "sufficient_info": 0.12,
        "high_impact": 0.30,
        "needs_escalation": 0.25,
        "action": "investigate",
    }.get(name, 0.9 if q["type"] == "noul" else next(iter(q["criteria"])))


# ── format_state ──────────────────────────────────────────────────────────────


def test_format_state_contains_all_fields():
    from agent.decision import format_state

    state = format_state(
        title="Login fails",
        description="500 error on login",
        error_message="HTTP 500",
        users_affected="500",
        severity="High",
        steps_to_reproduce="1. Enter credentials. 2. Click login.",
        workaround="None",
    )
    assert "Login fails" in state
    assert "500 error on login" in state
    assert "HTTP 500" in state
    assert "Users affected: 500" in state
    assert "Severity: High" in state
    assert state.startswith("A software bug report submitted for triage.")


def test_format_state_missing_fields_show_placeholder():
    from agent.decision import format_state

    state = format_state(
        title="Crash",
        description="",
        error_message="",
        users_affected="",
        severity="",
        steps_to_reproduce="",
        workaround="",
    )
    assert "(not provided)" in state


# ── BugTriagePolicy ───────────────────────────────────────────────────────────


def test_policy_escalates_high_impact_complete_bug():
    from agent.decision import format_state

    policy = make_policy(high_impact_complete_rule)
    state = format_state("Login failure", "500 for 500 users", "HTTP 500", "500", "High",
                         "Enter credentials, click login", "None")
    verdict = policy.check(state)
    assert verdict.action == "escalate"
    assert verdict.priority in ("Critical", "High")
    assert verdict.needs_escalation is True
    assert verdict.high_impact is True
    assert verdict.sufficient_info is True


def test_policy_prioritizes_low_impact_bug():
    from agent.decision import format_state

    policy = make_policy(low_impact_complete_rule)
    state = format_state("Typo in label", "Label says 'Invlaid'", "None", "10", "Low",
                         "Enter wrong password", "N/A")
    verdict = policy.check(state)
    assert verdict.action == "prioritize"
    assert verdict.priority in ("Low", "Medium")
    assert verdict.needs_escalation is False
    assert verdict.high_impact is False


def test_policy_requests_info_when_report_incomplete():
    from agent.decision import format_state

    policy = make_policy(missing_info_rule)
    state = format_state("Crash", "(not provided)", "(not provided)", "(not provided)",
                         "(not provided)", "(not provided)", "None known")
    verdict = policy.check(state)
    assert verdict.action == "request_info"
    assert verdict.sufficient_info is False


def test_policy_escalates_conflicting_signals():
    """High severity + very few users + unclear info → escalate (not guess)."""
    from agent.decision import format_state

    policy = make_policy(conflicting_signals_rule)
    state = format_state("Critical crash", "Reporter says critical", "Unknown JS error",
                         "1", "Critical", "(not provided)", "None")
    verdict = policy.check(state)
    # Conflicting signals → needs_escalation wins
    assert verdict.action == "escalate"
    assert verdict.needs_escalation is True


def test_policy_requests_info_for_unclear_error():
    from agent.decision import format_state

    policy = make_policy(unclear_error_rule)
    state = format_state("Something broken", "It stopped working", "(not provided)",
                         "(not provided)", "Medium", "(not provided)", "None")
    verdict = policy.check(state)
    # Insufficient info wins over investigate
    assert verdict.action == "request_info"
    assert verdict.sufficient_info is False


def test_policy_logs_one_record_per_call():
    from agent.decision import format_state

    policy = make_policy()
    state = format_state("Bug A", "Desc A", "Error A", "10", "Medium", "Steps A", "None")
    assert len(policy.log) == 0
    policy.check(state)
    assert len(policy.log) == 1
    policy.check(state)
    assert len(policy.log) == 2


def test_log_record_has_required_keys():
    from agent.decision import format_state

    policy = make_policy(high_impact_complete_rule)
    state = format_state("Bug", "Desc", "Err", "100", "High", "Steps", "None")
    policy.check(state)
    rec = policy.log[0]
    for key in ("pattern", "action", "priority", "sufficient_info", "high_impact",
                "needs_escalation", "action_confidence", "verdict", "decider_ms"):
        assert key in rec, f"missing key: {key}"
    assert rec["pattern"] == "#policy"


def test_decider_called_once_per_check():
    from agent.decision import format_state

    fake = FakeDecider()
    from agent.decision import BugTriagePolicy

    policy = BugTriagePolicy(fake)
    state = format_state("Bug", "Desc", "Err", "50", "High", "Steps", "None")
    assert len(fake.calls) == 0
    policy.check(state)
    assert len(fake.calls) == 1  # all four questions in one call


def test_priority_assignment_critical():
    """p_impact >= 0.8 + prioritize action → Critical."""
    from agent.decision import _assign_priority

    assert _assign_priority("prioritize", True, 0.85, 0.1) == "Critical"


def test_priority_assignment_high_escalate():
    """escalate + p_esc < 0.7 → High."""
    from agent.decision import _assign_priority

    assert _assign_priority("escalate", True, 0.9, 0.65) == "High"


def test_priority_assignment_critical_escalate():
    """escalate + p_esc >= 0.7 → Critical."""
    from agent.decision import _assign_priority

    assert _assign_priority("escalate", True, 0.9, 0.75) == "Critical"


def test_priority_assignment_medium_request_info():
    from agent.decision import _assign_priority

    assert _assign_priority("request_info", False, 0.2, 0.1) == "Medium"


def test_priority_assignment_low():
    from agent.decision import _assign_priority

    assert _assign_priority("prioritize", False, 0.1, 0.05) == "Low"


# ── eval_cases sanity check ───────────────────────────────────────────────────


def test_eval_cases_have_correct_question_keys():
    import json

    from agent.decision import QUESTIONS

    cases_path = ROOT / "agent" / "eval_cases.jsonl"
    lines = [l for l in cases_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 24, f"Expected ≥24 eval cases, got {len(lines)}"

    test_lines = [l for l in lines if '"test"' in l]
    assert len(test_lines) >= 12, f"Expected ≥12 test-split cases, got {len(test_lines)}"

    for line in lines:
        case = json.loads(line)
        assert set(case["expected"]).issubset(set(QUESTIONS)), (
            f"Unknown question keys: {set(case['expected']) - set(QUESTIONS)}"
        )
        assert isinstance(case["state"], str) and case["state"].strip()
        assert case.get("split") in ("tune", "test"), f"Missing or invalid split: {case}"


# ── decision.py contract ──────────────────────────────────────────────────────


def test_pattern_tag_is_policy():
    from agent.decision import PATTERN_TAG

    assert PATTERN_TAG == "#policy"


def test_questions_are_well_typed():
    from agent.decision import QUESTIONS

    assert "sufficient_info" in QUESTIONS
    assert "high_impact" in QUESTIONS
    assert "needs_escalation" in QUESTIONS
    assert "action" in QUESTIONS

    for name, q in QUESTIONS.items():
        assert q["type"] in ("noul", "choice", "score"), f"{name} has unknown type"
        assert "instructions" in q

    # noul questions must have criteria
    for name in ("sufficient_info", "high_impact", "needs_escalation"):
        assert "criteria" in QUESTIONS[name], f"{name} missing criteria"

    # action must be a choice with the four expected options
    action_opts = set(QUESTIONS["action"]["criteria"].keys())
    assert action_opts == {"prioritize", "request_info", "investigate", "escalate"}


def test_no_is_kit_example_flag():
    src = (ROOT / "agent" / "decision.py").read_text()
    assert "IS_KIT_EXAMPLE" not in src, "IS_KIT_EXAMPLE must be removed from the participant's decision.py"


def test_docstring_starts_correctly():
    import ast

    src = (ROOT / "agent" / "decision.py").read_text()
    doc = ast.get_docstring(ast.parse(src))
    assert doc and doc.startswith("REUSABLE DECISION PATTERN:")
