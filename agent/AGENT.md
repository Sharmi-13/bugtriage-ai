# BugTriage AI

**Pitch:** An AI-powered bug triage agent for software developers and QA teams — surfaces
priority, flags missing info, and recommends the right next action before a human has to read
the ticket.

## Who it is for

Software developers, QA engineers, and engineering managers who receive raw bug reports and
need to quickly decide: is this critical? Is there enough information? Should it go to on-call?

## The problem it solves

Manual triage is slow and inconsistent. A junior engineer might miss that 500 users are locked
out; a senior engineer might over-escalate a cosmetic glitch. BugTriage AI applies a consistent
decision policy on every ticket the moment it arrives.

## Features

- Accept a natural-language bug report (title, description, error message, affected users,
  severity, reproduction steps, workaround)
- Ask Strands Decider 2B to classify the report before the LLM responds
- Determine: is the report complete enough to act on? Is the evidence strong? How critical is
  the impact? Should a human review this immediately?
- Recommend one of four actions: Prioritize, Request Information, Investigate, or Escalate
- Return a priority level (Critical / High / Medium / Low) and the reasoning behind it
- Handle conflicting signals (e.g. high reported severity but only 1 user affected) safely by
  escalating to human review rather than guessing

## The decision (Strands Decider 2B)

**Pattern:** `#policy`

Before the LLM composes its reply, Strands Decider 2B reads the full bug report state and
answers four typed questions in a single call:

| Question | Type | What it measures |
|---|---|---|
| `sufficient_info` | noul | Is there enough evidence to make a triage decision? |
| `high_impact` | noul | Does the reported impact suggest a high-priority issue? |
| `needs_escalation` | noul | Does this require immediate human review? |
| `action` | choice | What is the right next action: prioritize / request_info / investigate / escalate? |

The four answers drive the triage workflow. The LLM only composes the explanation — it never
overrides the decider's verdict.

## Amazon Bedrock

The agent is paired with Amazon Bedrock (Amazon Nova Pro) for the deployed submission. During
development it runs on the AWS User Group Madurai cloud (Qwen3.5-4B) via the same Strands
Agents SDK.

## Data

Synthetic bug reports — no external database or API required. All data lives in
`agent/data/bugs.json`.

## Built with

Built with the AWS User Group Madurai Strands Decider hackathon kit.
