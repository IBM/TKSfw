# ADR 0007 — Activity plan: rules stay in AGENTS.md, grammar and procedure move to `yaml-log-entry`, syntax becomes hook-enforced

Date: 2026-09-06 · Status: accepted

## Context
§ Activity Plan (2.5 KB) mixed five rules used at every read/write of `tasks.md` (location and purpose,
document order, source of truth vs harness task tools, evidence link, keep-it-lean) with a schema block,
the evidence details (leaf definition, terminal-positive pairs, which tool checks what) and the archive
procedure. The format was already machine-checked by `tasks_parse.py`/`tasks_lint.py`/`cross_check.py`,
but the lint was advisory and not run on writes.

## Decision
| Choice | Rationale |
|---|---|
| Rules stay in AGENTS.md (5 lines) | they govern every plan read ("next task") and write ("[ev:]", SoT) |
| Grammar, evidence table, archive procedure → `yaml-log-entry/references/tasks.md` | that skill already owns the plan tooling and STATE.md imports its parser; a separate skill would duplicate the parser or couple skills |
| `tasks_lint.py` severity split: ERROR (syntactic) / WARN (evidence); `--json` | deterministic findings can block, SHOULD-rules stay advisory |
| `track_edits.py` runs the lint on live `tasks.md` writes: ERROR → exit 2 with the grammar; WARN → systemMessage | same self-healing pattern as ledger validation and agent definitions |
| `tasks-archive.md` never linted | frozen history |
| STATE.md "Archivable plan blocks" hint | the archive step has no write-time trigger; make it visible instead |

## Consequences
- AGENTS.md 17,715 → 16,514 B (−1.2 KB); kernel is ~16.5 KB against the 32 KiB budget.
- A malformed plan line is now impossible to persist unnoticed on either harness.
- Codex: re-trust hooks after updating (`track_edits.py`, `refresh_state.py` changed).
