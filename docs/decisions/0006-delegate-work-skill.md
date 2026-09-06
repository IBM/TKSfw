# ADR 0006 — Delegation: decision rules stay in AGENTS.md, mechanics move to `delegate-work`, limits move to hooks

Date: 2026-09-06 · Status: accepted

## Context
After ADR 0003/0004 the § Subagents / § Agent Naming text was 3.5 KB. Reviewing it line by line: most
lines are DECISION rules used at every delegation (check existing agents, one task per agent, disjoint
ownership, no nesting, ≤ 4 parallel, validation in a fresh context, `judge` only for judgement). Five
lines were PROCEDURE used only after the decision (worktree vs work area, cleanup/prune, how to change
models, persist agent files) and two rules relied on model discipline although they are mechanically
checkable (no nested spawns, ≤ 4 parallel).

## Decision
| Choice | Rationale |
|---|---|
| Decision rules stay in AGENTS.md | a skill "for delegation" would load in nearly every non-trivial turn — no context saving, one more hot-path step |
| Procedure moves to the `delegate-work` skill (`references/isolation.md`, `assets/workarea.py`) | needed only once parallel/isolated work is chosen; gets a helper instead of prose (create/list/prune worktrees and work areas, refuse unmerged, `.gitignore` for worktrees) |
| `[delegation] max_parallel_agents` / `deny_nested_spawn` in `models.toml`, enforced by `route_model.py`; `subagent_track.py` on SubagentStart/Stop | the two limits become guarantees; single config file for spawn-time policy |
| Stop hook clears the live set and reports stale isolation | a missed SubagentStop cannot wedge spawns; cleanup omissions become visible |
| `.agents/worktrees/` never watched | worktree copies of framework files must not register as framework edits |

## Consequences
- AGENTS.md shrinks by only ~0.3 KB; the gain is reliability, not budget (§ Subagents remains 12 lines).
- Nested-spawn detection depends on harness payload fields; it is fail-open per field and switchable.
- New hook events require re-trust in Codex `/hooks` after updating.
