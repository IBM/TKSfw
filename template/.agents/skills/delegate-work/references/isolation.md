# Delegation mechanics — isolation, work areas, cleanup, model changes (method reference)

Moved from `AGENTS.md` § Subagents / § Agent Work Areas (1.2.0). The DECISION rules stay in AGENTS.md
(when to delegate, one task per agent, disjoint ownership, no nesting, ≤ 4 parallel, validation in a
fresh context, `judge` tier only for judgement). This file holds the PROCEDURE that applies once the
decision is made. Two of the decision rules are also enforced by the `route_model.py` PreToolUse hook:
a spawn from inside a subagent is refused, and the 5th concurrent spawn of a turn is refused
(`[delegation] max_parallel_agents` in `.agents/config.toml`).

## Isolation

- Each subagent must own distinct files/directories (state the ownership matrix in the handoff).
- Isolation key (1.4.0): `<session-token>.<task-id>.<instance>`. The session token is minted by the
  SessionStart hook and shown in context (two sessions on one project never collide); the instance
  number (allocated by the helper, `0 … max_parallel_agents-1`, never chosen by hand) separates parallel
  copies of the same agent on the same task. `<task-id>` alone was an ownership key, not a concurrency key.
- Use git worktrees for stricter isolation when available and parallel writes are possible:
  `python3 .agents/skills/delegate-work/assets/workarea.py create <agent> <task-id> --session <token> --worktree`
  → `.agents/worktrees/<agent>--<key>` on branch `agent/<agent>/<key>`.
- If git worktrees are unavailable (no git, Box-synced folder, nested repo), fall back to strict
  directory-based file ownership and give the agent a work area to keep the main project folder clean:
  `… create <agent> <task-id> --session <token>` → `.agents/workarea/<agent>/<key>/`.
- `--instance N` reuses an existing instance (retry after a failed spawn); `--session` may be omitted
  only when exactly one session is active on the project.
- A subagent operating in a worktree or work area writes its ledger entries and `tasks.md` status to
  the canonical `.agents/workarea/` (project root), never to a worktree-local copy. Agent work areas
  (`.agents/workarea/<agent>/…`) are NOT watched by the edit-hash hook and never count as deliverables.

## Handoff protocol

1. `handoffs.yaml` BEGIN entry (via `yaml-log-entry`): `AgentName`, `Model` (the value the routing hook
   reports), scope, owned paths, success criteria, `TaskID`.
2. Spawn (the hook injects the model; record what it reports).
3. On return: `handoffs.yaml` END entry + `events.yaml` entry; merge/validate; mark the task in `tasks.md`.
4. Clean up: `… prune <agent> <task-id> [--session T] [--instance N]` (removes the worktree — refusing
   if the branch is not merged unless `--force` — or the work area); `… prune --session <token>` at
   session end. Periodically `… prune --stale` removes work areas whose task is COMPLETED in `tasks.md`
   and worktrees whose branch is merged. The Stop hook lists stale ones.
5. Record the work area path in the handoff BEGIN entry (`Scope` or `Inputs`), so the instance is
   traceable from the ledger, not only from disk.

## Agent definitions

- Persist agent files (`.agents/agents/<name>.toml`) in the repo so they are reused across sessions,
  not recreated each time (`define-agent` owns the format).

## Changing models

- Models change only by editing `.agents/config.toml` (a METHOD-layer change, logged in `changes.yaml`)
  — never an agent file, never AGENTS.md. Do it only while no subagent is running; then run
  `python3 .agents/hooks/sync_harness.py --models` to re-render the harness copies of the agent
  definitions. The next spawn uses the new mapping; no restart or hook re-trust is needed
  (`docs/model-routing.md`).
