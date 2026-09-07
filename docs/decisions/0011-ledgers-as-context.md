# ADR 0011 — Ledgers as context: digest in STATE.md, subagent briefing, consult-before-deciding

Date: 2026-09-07 · Status: accepted

## Context
Until 1.9 the framework was strong on writing ledgers and weak on reading them back: STATE.md carried
counts and IDs (open decisions, open issues, dangling handoffs), lessons were "review at session start" by
instruction only, ACCEPTED decisions — the constraints in force — were never surfaced, and failed gates
(REVIEW FAIL, TEST KO, AUDIT NON-CONFORMANT, APPROVAL NO-GO) were invisible. Workers knew only what the
orchestrator typed into the spawn prompt.

## Decisions
| Choice | Rationale |
|---|---|
| A **ledger digest** (`digest.py`, skill asset) with fixed sections in priority order: blocked gates, decisions in force, pending decisions, open issues, work in flight, recent lessons, recent changes | Content, not IDs; the order puts what blocks or constrains work first |
| Selection by status, recency and explicit IDs (TaskID, DecisionID, RelatedTo) — never by similarity | Deterministic and auditable; std lib; what an agent was shown can be reconstructed |
| Digest embedded in STATE.md (injected on every start/resume/compaction) within `[state].budget_chars` (3,500 default); whole injection stays under 9,000 chars | Both harnesses cap hook output at 10,000 chars and spill the rest to a file the model may never open |
| Truncation drops the lowest-priority items first; a "… N more (`ks ledger digest`)" line points to the full view | Content that does not fit is worse than a pointer |
| `SubagentStart` briefing (`digest.py --agent`): the Worker's open handoff BEGIN, its task's evidence chain, blocked gates, **all** decisions in force, open issues on the task, recent lessons; budget `[state].subagent_budget_chars` | Both harnesses inject `additionalContext` into the subagent at start; the ledger becomes the Worker's second source of truth, deterministically |
| Prompt notice announces new open issues and failed gates as they appear | Blockers surface when they happen, not at the next restart |
| Method rule "Consult before deciding": read the digest before planning/deciding; `SUPERSEDED` transition before contradicting an ACCEPTED decision; handoff BEGIN lists decision/lesson IDs in `Inputs` | Reading gets a trigger, as writing already has |
| Not done: semantic retrieval, verification that the model read | Out of scope for a deterministic, stdlib framework; a `Tags` field on lessons is the next step if volumes grow |

## Consequences
- AGENTS.md 18,858 B (one rule added, one shortened).
- Major version 2.0.0: together with the 1.4 (owner fields), 1.7 (partitioned ledgers, append-only decisions, per-host state) and 1.9 (reset/generations) changes this defines the 2.x project format; see CHANGELOG "Upgrading from 1.x".
