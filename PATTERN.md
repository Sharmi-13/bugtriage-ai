\# Reusable Decider 2B decision pattern: bug triage (#policy)



Pattern tag: `#policy` (classify an incoming request before the agent acts on it)

Code: `agent/decision.py`



\## The decision



Strands Decider 2B reads a formatted bug report and answers four typed questions in one call:



| Question | Type | Options |

|---|---|---|

| sufficient\_info | yes/no | is the report complete enough to triage? |

| high\_impact | yes/no | many users, severe error, no workaround? |

| needs\_escalation | yes/no | conflicting signals or outage-level impact? |

| action | choice | prioritize, request\_info, investigate, escalate |



Plain code (not the LLM) turns the answers into a priority: Critical, High, Medium or Low.

The LLM only explains the verdict and never overrides it.



\## Wiring



1\. The agent formats the user's message into a standard state with the `format\_bug\_report` tool.

2\. `BugTriagePolicy.check(state)` sends the state and all four questions to Decider 2B in one request.

3\. The verdict (action, priority, confidences) is passed to the LLM, which writes the explanation.

4\. Greetings such as "hi" skip this path.



```python

policy = BugTriagePolicy(decider)

verdict = policy.check(state\_text)

\# verdict.action, verdict.priority, verdict.log\_record

```



\## How to reuse it



1\. Copy `agent/decision.py`.

2\. Rewrite `QUESTIONS` for your domain and reword the option descriptions.

3\. Adjust the thresholds (`escalate\_at`, `high\_impact\_at`, `info\_at`) and `\_assign\_priority`. They are ordinary `if` statements you own.

4\. Keep the state layout the same at runtime and in your eval cases.

