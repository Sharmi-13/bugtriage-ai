# BugTriage AI — Requirements

## Users
Software developers, QA engineers, and engineering managers who receive raw bug reports.

## User stories

1. WHEN a user submits a bug report with all required fields, THE agent SHALL ask Strands
   Decider 2B whether the report has sufficient information, whether the impact is high,
   whether escalation is needed, and what action to take BEFORE the LLM composes its reply.

2. WHEN the decider determines the report lacks sufficient information, THE agent SHALL
   recommend the "request_info" action and list the missing fields.

3. WHEN the decider determines the impact is high and escalation is needed, THE agent SHALL
   recommend "escalate" and assign Critical or High priority, regardless of LLM output.

4. WHEN the decider confidence on `needs_escalation` is below 0.5, THE agent SHALL NOT
   escalate based on that signal alone.

5. WHEN the report contains conflicting signals (e.g. "Critical" severity but 1 user affected
   and no steps to reproduce), THE agent SHALL ask Strands Decider 2B to resolve the conflict
   and escalate if the decider indicates uncertainty.

6. WHEN the agent assigns a priority, THE priority SHALL be determined by code using the
   decider's verdicts — not by the LLM — using the scheme:
   - Critical: escalate + p_escalation ≥ 0.7, or prioritize + p_impact ≥ 0.8
   - High: escalate + p_escalation < 0.7, or investigate + high_impact
   - Medium: request_info, or investigate without high_impact
   - Low: prioritize + p_impact < 0.3

7. THE agent SHALL clearly distinguish observed facts from inferences in its reply.

8. THE agent SHALL be paired with Amazon Bedrock for the deployed submission.

9. THE agent SHALL work with the AWS User Group Madurai cloud (Qwen3.5-4B) during development.
