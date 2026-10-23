# BugTriage AI — Tasks

- [x] Write AGENT.md (pitch, features, decision, data source)
- [x] Write agent/decision.py (PATTERN_TAG=#policy, QUESTIONS, BugTriagePolicy, format_state)
- [x] Write agent/tools.py (lookup_bug, list_bugs, format_bug_report)
- [x] Write agent/agent.py (HackathonAgent, chat(), NAME, SYSTEM_PROMPT)
- [x] Write agent/data/bugs.json (6 synthetic bug reports)
- [x] Write agent/eval_cases.jsonl (24 cases, 12 tune / 12 test)
- [x] Write agent/demo_script.yaml (4 turns covering all decision paths)
- [x] Write agent/features.yaml (Memory and Gateway disabled)
- [x] Write .kiro/specs/bug-triage-ai/requirements.md
- [x] Write tests/test_bug_triage.py (wiring test with FakeDecider)
- [x] Run ./kit test — fix until green (25/25 passed)
- [ ] Run ./kit run — verify end-to-end conversation
- [ ] Run ./kit bench --split tune — tune questions if needed
- [ ] Run ./kit bench --split test — record final numbers
