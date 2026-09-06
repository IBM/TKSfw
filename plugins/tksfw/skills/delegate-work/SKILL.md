---
name: delegate-work
description: >
  Mechanics for delegating work to subagents once the decision to delegate has been made (AGENTS.md
  § Subagents holds the decision rules): isolation (git worktree or agent work area), ownership matrix,
  handoff BEGIN/END logging, cleanup and pruning of finished worktrees/work areas, and how to change
  models via .agents/models.toml. Load when parallelising subagents, when a subagent needs an isolated
  place to write, when cleaning up after a phase, or when the Stop hook reports stale work areas.
---

# Delegate work — isolation, handoff, cleanup

The rules that decide *whether* and *how many* subagents run stay in `AGENTS.md`; two of them are
enforced by the routing hook (no nested spawns; at most `max_parallel_agents` concurrent). This skill
owns what happens after the decision. Full text: `references/isolation.md`.

## Procedure

1. Ownership matrix: list each agent with the paths it owns; overlapping paths → chain sequentially.
2. Isolation per agent:
   `python3 .agents/skills/delegate-work/assets/workarea.py create <agent> <task-id> [--worktree]`
   (worktree when git is available and parallel writes are needed; otherwise a work area under
   `.agents/workarea/<agent>/<task-id>/`). The command prints the path to hand to the agent.
3. Log the handoff BEGIN (`yaml-log-entry`), spawn, log END + event on return.
4. Clean up: `… prune <agent> <task-id>` after merge/validation; `… list` and `… prune --stale`
   (COMPLETED tasks / merged branches) at phase end. Never leave a worktree with unmerged work
   unlogged — `prune` refuses unless `--force`.

## Tools

| Asset | Use |
|---|---|
| `assets/workarea.py create <agent> <task-id> [--worktree]` | create the isolated place; idempotent |
| `assets/workarea.py list [--json]` | worktrees and work areas with staleness (task COMPLETED / branch merged) |
| `assets/workarea.py prune <agent> <task-id> [--force]` · `prune --stale [--dry-run]` | remove |
| `references/isolation.md` | the moved method text |
