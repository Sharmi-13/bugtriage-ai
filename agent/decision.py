"""REUSABLE DECISION PATTERN: bug triage policy  (#policy)

What it does
    Before the support agent composes its reply, Strands Decider 2B reads the full bug
    report and answers four typed questions in one forward pass:

    - Is there sufficient information to make a triage decision?
    - Does the reported impact suggest a high-priority issue?
    - Does this require immediate human/on-call escalation?
    - What is the right next action: prioritize, request more info, investigate, or escalate?

    These four answers drive the triage workflow. The LLM only composes the explanation —
    it never overrides the decider's verdict. Conflicting signals (e.g. high severity
    but only 1 user) route to escalate rather than guessing.

Typed questions and options
    sufficient_info (noul): Is the bug report complete enough to act on?
        true  – enough information is present: title, description, error, affected count,
                severity, and at least partial steps to reproduce
        false – one or more critical fields are missing or too vague to triage

    high_impact (noul): Does the reported impact suggest this is high-priority?
        true  – the evidence points to significant impact: many users affected, severe
                error (5xx, crash, data loss), no workaround, or a critical business area
        false – the impact appears limited: few users, cosmetic issue, workaround exists,
                or unclear error

    needs_escalation (noul): Should this be reviewed by a human or on-call engineer
                              immediately, rather than handled by automated triage?
        true  – the issue shows conflicting signals, extremely high impact (500+ users,
                production outage, security concern), or the evidence alone is insufficient
                to safely determine the next action
        false – the evidence is clear enough for automated triage to proceed

    action (choice): What is the right next action for this bug report?
        prioritize     – enough info and impact is clear; assign a priority level and add
                         to the backlog
        request_info   – key information is missing; ask the reporter before acting
        investigate    – information is present but the cause or scope is uncertain;
                         recommend specific diagnostic steps
        escalate       – impact is critical or signals conflict; route to a human
                         immediately

Wiring
    `BugTriagePolicy` is called inside `HackathonAgent.chat()`, before the Strands Agent
    runs. It reads the formatted bug report state and returns a `TriageVerdict` that is
    injected into the system prompt context so the LLM explains (not overrides) the decision:

        policy = BugTriagePolicy(decider)
        verdict = policy.check(state_text)
        # verdict.action, verdict.priority, verdict.log_record are passed to the Agent

    The decider is called once per bug submission. All four questions share one HTTP round
    trip (the state is encoded once).

How to reuse it
    Copy this file, rewrite QUESTIONS for your domain (replace "bug report" with your
    content type, and reword the option descriptions). The thresholds in `BugTriagePolicy`
    (`escalate_at`, `high_impact_at`) are ordinary `if` statements you own. The `TriageVerdict`
    dataclass carries everything the LLM needs to compose an explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from decider_kit import Decider
from decider_kit.client import Decision

PATTERN_TAG = "#policy"

QUESTIONS: dict[str, dict[str, Any]] = {
    "sufficient_info": Decider.noul(
        "Is the bug report complete enough to make a triage decision?",
        {
            "true": (
                "enough information is present: the report has a title, a description, "
                "an error message or observable symptom, an affected-user count, a severity "
                "rating, and at least partial reproduction steps"
            ),
            "false": (
                "one or more critical fields are absent or too vague: the description is "
                "a single word, the error is unknown, the user count is missing, or there "
                "are no reproduction steps at all"
            ),
        },
    ),
    "high_impact": Decider.noul(
        "Does the reported impact suggest this is a high-priority issue?",
        {
            "true": (
                "the evidence points to significant impact: many users are affected "
                "(roughly 50 or more), the error is severe (HTTP 5xx, crash, data loss, "
                "security breach), there is no known workaround, or a critical business "
                "function is completely blocked"
            ),
            "false": (
                "the impact appears limited: very few users are affected, the issue is "
                "cosmetic or minor, a workaround already exists, or the error type is "
                "low-severity (e.g. a UI label, a warning message, a non-blocking 4xx)"
            ),
        },
    ),
    "needs_escalation": Decider.noul(
        "Should this bug be routed to a human or on-call engineer for immediate review?",
        {
            "true": (
                "escalation is needed: the issue shows conflicting signals that automated "
                "triage cannot safely resolve, or the potential impact is extremely high "
                "(production outage, security vulnerability, data corruption, 500+ users "
                "blocked with no workaround), or the evidence available is insufficient "
                "to determine the right next action with confidence"
            ),
            "false": (
                "automated triage can proceed safely: the signals are consistent, the "
                "impact and severity are clear, and the right next action is evident "
                "from the available evidence"
            ),
        },
    ),
    "action": Decider.choice(
        "What is the most appropriate next action for this bug report?",
        {
            "prioritize": (
                "the report has sufficient information, the impact and severity are clear, "
                "and the bug should be assigned a priority level and added to the backlog "
                "for the engineering team to fix"
            ),
            "request_info": (
                "the report is missing key details needed to assess or reproduce the bug; "
                "the reporter should be asked to provide the missing information before "
                "any further action is taken"
            ),
            "investigate": (
                "the report has enough information to act on, but the root cause, scope, "
                "or severity is uncertain; a developer or QA engineer should run specific "
                "diagnostic steps before assigning a final priority"
            ),
            "escalate": (
                "the bug requires immediate human attention: it may be a production "
                "outage, a security issue, a data-integrity problem, or the signals in "
                "the report are contradictory and cannot be safely resolved by automated "
                "triage alone"
            ),
        },
    ),
}

# Priority levels assigned by code (not by the LLM) based on decider verdicts + facts in the
# report.  These thresholds are ordinary if-statements the kit owner controls.
PRIORITY_CRITICAL = "Critical"
PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_LOW = "Low"


@dataclass
class TriageVerdict:
    """The result of one decider call on a bug report."""

    action: str          # prioritize | request_info | investigate | escalate
    priority: str        # Critical | High | Medium | Low
    sufficient_info: bool
    high_impact: bool
    needs_escalation: bool
    p_sufficient: float
    p_high_impact: float
    p_escalation: float
    action_confidence: float
    decider_ms: float
    answers: dict[str, Decision] = field(repr=False, default_factory=dict)

    @property
    def log_record(self) -> dict[str, Any]:
        return {
            "pattern": PATTERN_TAG,
            "action": self.action,
            "priority": self.priority,
            "sufficient_info": round(self.p_sufficient, 3),
            "high_impact": round(self.p_high_impact, 3),
            "needs_escalation": round(self.p_escalation, 3),
            "action_confidence": round(self.action_confidence, 3),
            "verdict": self.action,
            "decider_ms": round(self.decider_ms),
        }


class BugTriagePolicy:
    """Call Strands Decider 2B on a bug report state and return a TriageVerdict.

    All four questions are sent in one HTTP request. The verdict drives the agent's
    reply; the LLM only explains the decision.

    Args:
        decider: a configured Decider instance.
        escalate_at: p_yes threshold above which `needs_escalation` is considered true.
        high_impact_at: p_yes threshold above which `high_impact` is considered true.
        info_at: p_yes threshold above which `sufficient_info` is considered true.
    """

    def __init__(
        self,
        decider: Decider,
        escalate_at: float = 0.5,
        high_impact_at: float = 0.5,
        info_at: float = 0.5,
    ):
        self.decider = decider
        self.escalate_at = escalate_at
        self.high_impact_at = high_impact_at
        self.info_at = info_at
        self.log: list[dict[str, Any]] = []

    def check(self, state: str) -> TriageVerdict:
        """Run the decider on `state` and return a TriageVerdict.

        `state` must be the formatted bug report text produced by `format_state()` in
        tools.py — the same layout the eval cases use.
        """
        a = self.decider.ask(state, QUESTIONS)

        p_info = a["sufficient_info"].p_yes or 0.0
        p_impact = a["high_impact"].p_yes or 0.0
        p_esc = a["needs_escalation"].p_yes or 0.0
        action_label = a["action"].label or "investigate"
        action_conf = a["action"].confidence

        sufficient = p_info >= self.info_at
        impactful = p_impact >= self.high_impact_at
        escalate = p_esc >= self.escalate_at

        # Override action with escalate when the decider says so, regardless of `action` label.
        # This prevents the LLM from overriding a clear escalation signal.
        if escalate:
            final_action = "escalate"
        elif not sufficient:
            final_action = "request_info"
        else:
            final_action = action_label

        # Priority is assigned by code, not by the LLM, based on the decider's verdicts.
        priority = _assign_priority(final_action, impactful, p_impact, p_esc)

        verdict = TriageVerdict(
            action=final_action,
            priority=priority,
            sufficient_info=sufficient,
            high_impact=impactful,
            needs_escalation=escalate,
            p_sufficient=p_info,
            p_high_impact=p_impact,
            p_escalation=p_esc,
            action_confidence=action_conf,
            decider_ms=self.decider.last_latency_ms or 0.0,
            answers=a,
        )
        self.log.append(verdict.log_record)
        return verdict


def _assign_priority(action: str, high_impact: bool, p_impact: float, p_esc: float) -> str:
    """Assign a priority level from the triage action and impact signals.

    This is pure code — no LLM or decider involved in this step.
    """
    if action == "escalate":
        return PRIORITY_CRITICAL if p_esc >= 0.7 else PRIORITY_HIGH
    if action == "request_info":
        # Can't fully assess without info, default to medium; escalation already handled above
        return PRIORITY_MEDIUM
    if action == "investigate":
        return PRIORITY_HIGH if high_impact else PRIORITY_MEDIUM
    # action == "prioritize"
    if p_impact >= 0.8:
        return PRIORITY_CRITICAL
    if high_impact:
        return PRIORITY_HIGH
    if p_impact >= 0.3:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def format_state(
    title: str,
    description: str,
    error_message: str,
    users_affected: str,
    severity: str,
    steps_to_reproduce: str,
    workaround: str,
) -> str:
    """Build the state string sent to Strands Decider 2B.

    This exact layout is used both at runtime and in eval_cases.jsonl.
    """
    return (
        "A software bug report submitted for triage.\n\n"
        f"Title: {title or '(not provided)'}\n"
        f"Description: {description or '(not provided)'}\n"
        f"Error message: {error_message or '(not provided)'}\n"
        f"Users affected: {users_affected or '(not provided)'}\n"
        f"Severity: {severity or '(not provided)'}\n"
        f"Steps to reproduce: {steps_to_reproduce or '(not provided)'}\n"
        f"Workaround: {workaround or 'None known'}"
    )
