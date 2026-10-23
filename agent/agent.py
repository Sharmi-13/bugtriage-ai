"""BugTriage AI: Strands Decider 2B classifies the bug report, the LLM explains the verdict.

How it works
    1. The user submits a bug report (freeform message or structured fields).
    2. The agent uses tools to extract/format the bug into the standard state text.
    3. BugTriagePolicy calls Strands Decider 2B on that state (one HTTP round trip,
       four typed questions).
    4. The verdict (action, priority, decider probabilities) is injected into the
       system prompt context.
    5. The LLM (Qwen3.5-4B on the user group cloud, Nova Pro on Bedrock) composes
       a clear explanation of the decision — it does not override it.

    from agent.agent import HackathonAgent
    out = HackathonAgent().chat("Login fails with 500 for ~500 users after today's deploy. No workaround.")
    out["reply"], out["decisions"]
"""

from __future__ import annotations

import time
from typing import Any

from strands import Agent

from decider_kit import Decider
from decider_kit.llm import agent_model, default_model_id, strip_thinking

from .decision import BugTriagePolicy, format_state
from .tools import TOOLS

NAME = "BugTriage AI"

SYSTEM_PROMPT = """You are BugTriage AI, an expert software bug triage assistant for developers and QA teams.

Your job is to help users analyse bug reports and decide what to do next.

You have access to these tools:
- lookup_bug: retrieve a known bug by ID from the dataset
- list_bugs: list all known bugs
- format_bug_report: format a user's bug details into the structured triage state

IMPORTANT: When a user provides bug details, first call format_bug_report with those details.
The system will then run Strands Decider 2B on the formatted report and inject the triage
verdict into your context. You must then explain the verdict clearly using this structure:

**Recommended Priority:** <priority>
**Recommended Action:** <action>
**Reasoning:** <explain why, based on the evidence provided>
**Evidence used:** <list the key facts from the report>
**Missing information:** <list any fields that were absent or vague, if any>
**Recommended next steps:** <concrete steps for the engineering team>

If a verdict has already been computed (you will see TRIAGE VERDICT in your context),
explain it — do not re-call format_bug_report or make up your own verdict.

Be factual. Do not claim a root cause unless the evidence supports it.
Distinguish observed facts from inferences.
If information is missing, say so clearly instead of guessing."""


class HackathonAgent:
    """One Strands Agent per session, with Strands Decider 2B wired in before the LLM responds."""

    def __init__(
        self,
        decider: Decider | None = None,
        model_id: str | None = None,
        eager: bool | None = None,
    ):
        import os

        self.decider = decider or Decider()
        self.model_id = model_id or default_model_id()
        self.eager = eager if eager is not None else os.environ.get("DEMO_EAGER") == "1"
        self.sessions: dict[str, tuple[Agent, BugTriagePolicy]] = {}

    def _session(self, session_id: str) -> tuple[Agent, BugTriagePolicy]:
        if session_id not in self.sessions:
            policy = BugTriagePolicy(self.decider)
            agent = Agent(
                model=agent_model(self.model_id),
                system_prompt=SYSTEM_PROMPT,
                tools=TOOLS,
                callback_handler=None,
            )
            self.sessions[session_id] = (agent, policy)
        return self.sessions[session_id]

    def chat(self, message: str, session_id: str = "default", images: list[Any] | None = None) -> dict[str, Any]:
        """Triage a bug report.

        The agent calls format_bug_report, then BugTriagePolicy runs the decider, then
        the LLM composes the explanation. The decider verdict is always in `decisions`.
        """
        agent, policy = self._session(session_id)
        before = len(policy.log)
        t0 = time.perf_counter()
        if message.strip().lower().strip("!.? ") in {
            "hi", "hello", "hey", "hii", "hi there", "thanks", "thank you", "ok", "okay", "bye"
        }:
            return {
                "reply": "Hi! I'm BugTriage AI. Describe a bug (what fails, who is affected, any workaround) and I'll triage it.",
                "decisions": [],
                "model_id": self.model_id,
                "latency_ms": 0,
                "agent": NAME,
                "eager": self.eager,
            }

        # ── Step 1: let the LLM collect and format the bug report via tools ──────────────
        # We give the agent the user's message; it calls format_bug_report which returns
        # the structured state text. We intercept that state for the decider call.
        # To do this cleanly: we run the agent first to get the formatted state, then
        # inject the decider verdict back into a second (explanation) pass.

        # First pass: agent extracts/formats the bug report
        first_result = agent(message)
        first_reply = strip_thinking(str(first_result))

        # ── Step 2: extract the formatted state from the tool call, if available ─────────
        state_text = _extract_state_from_tool_calls(agent, message)

        verdict = None
        if state_text:
            # ── Step 3: run Strands Decider 2B on the formatted bug report ───────────────
            verdict = policy.check(state_text)

            # ── Step 4: inject the verdict into the agent context and get the explanation ─
            verdict_context = _format_verdict_context(verdict)
            explanation_prompt = (
                f"TRIAGE VERDICT from Strands Decider 2B:\n{verdict_context}\n\n"
                "Please explain this verdict to the user using the required format. "
                "Use only the evidence in the original bug report. "
                "Do not invent details that were not in the report."
            )
            second_result = agent(explanation_prompt)
            reply = strip_thinking(str(second_result))
        else:
            # No structured bug report extracted — agent asked for more info or listed bugs
            reply = first_reply

        decisions = policy.log[before:]
        return {
            "reply": reply,
            "decisions": decisions,
            "model_id": self.model_id,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "agent": NAME,
            "eager": self.eager,
        }


def _extract_state_from_tool_calls(agent: Agent, original_message: str) -> str | None:
    """Find the formatted bug state in the agent's tool results."""
    messages = getattr(agent, "messages", []) or []
    for msg in reversed(messages):
        for block in msg.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            result = block.get("toolResult")
            if not result:
                continue
            for item in result.get("content", []) or []:
                text = item.get("text", "") if isinstance(item, dict) else ""
                if isinstance(text, str) and text.startswith("A software bug report submitted for triage."):
                    return text
    return None

def _format_verdict_context(verdict: Any) -> str:
    """Build a plain-text summary of the TriageVerdict for the LLM context."""
    return (
        f"Action: {verdict.action}\n"
        f"Priority: {verdict.priority}\n"
        f"Sufficient information: {'yes' if verdict.sufficient_info else 'no'} "
        f"(confidence: {verdict.p_sufficient:.0%})\n"
        f"High impact: {'yes' if verdict.high_impact else 'no'} "
        f"(confidence: {verdict.p_high_impact:.0%})\n"
        f"Needs escalation: {'yes' if verdict.needs_escalation else 'no'} "
        f"(confidence: {verdict.p_escalation:.0%})\n"
        f"Action confidence: {verdict.action_confidence:.0%}\n"
        f"Decider latency: {verdict.decider_ms:.0f} ms"
    )


if __name__ == "__main__":
    import json
    import sys

    a = HackathonAgent()
    msgs = sys.argv[1:] or [
        "Login fails with HTTP 500 for ~500 users after today's deploy. No workaround.",
        "There's a UI label overlapping a button on mobile. Only 2 users saw it, landscape mode fixes it.",
    ]
    for msg in msgs:
        print(f"\n>>> {msg}")
        out = a.chat(msg)
        print(json.dumps({k: v for k, v in out.items() if k != "decisions"}, indent=2))
        if out["decisions"]:
            print("Decider decisions:", json.dumps(out["decisions"], indent=2))
