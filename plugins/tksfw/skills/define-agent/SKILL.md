---
name: define-agent
description: >
  Create, rename or edit a subagent definition (.agents/agents/<name>.toml) for this method: naming
  convention <family>-<role> with the role vocabulary from .agents/config.toml, required fields,
  description prefix, sandbox mode by tier, and the rule that models are never hand-written. Load
  BEFORE creating, renaming or editing ANY .agents/agents/*.toml — the PostToolUse hook validates every
  agent file on write (assets/validate_agent.py) and blocks non-conforming definitions; a rename must
  also be logged in changes.yaml.
---

# Define an agent

Owner of the agent-definition procedure and the naming convention (moved here from `AGENTS.md`
§ Subagents / § Agent Naming; the full text is `references/naming.md`).

## Procedure

1. Look for an existing agent by role in `.agents/agents/`; extend it rather than duplicate it.
2. Choose the name: `<family>-<role>`; `<role>` must be a key of `[roles]` in `.agents/config.toml`
   (the tier follows from it); `<family>` only when needed to disambiguate; ≤ 3 tokens; never `main`,
   never a harness built-in name, never a person or codename. Read `references/naming.md` when in doubt.
3. Write `.agents/agents/<name>.toml` with `name`, `description` ("Use PROACTIVELY when…" /
   "MUST BE USED for…"), `developer_instructions` (scope, file paths, success criteria, "return a
   concise structured summary"), `sandbox_mode` (`read-only` for researcher/reviewer/validator/planner,
   `workspace-write` for builder/writer/fetcher). Do **not** write `model` or `model_reasoning_effort`.
4. Validate: `python3 .agents/skills/define-agent/assets/validate_agent.py .agents/agents/<name>.toml`
   (the PostToolUse hook runs the same check and blocks on errors; warnings are advisory).
5. Harness mirrors (`.codex/agents/<name>.toml` with the routed model lines, `.claude/agents/<name>.md`)
   are rendered automatically by the PostToolUse hook once the file is valid — never edit them.
   Bulk re-render after changing `.agents/config.toml`: `python3 .agents/hooks/sync_harness.py --models`.
6. Log: a new or renamed agent is a `changes.yaml` entry (Layer CORE or ARCHETYPE per the
   `yaml-log-entry` skill); a rename must state old → new so the Handoff/Event `AgentName` history
   stays traceable.

## Tools

| Asset | Use |
|---|---|
| `assets/validate_agent.py <file>… [--models <path>] [--json]` | Errors (exit 2) and warnings (exit 0); also `--all` for every file in `.agents/agents/` |
| `references/naming.md` | The complete convention with the [E]/[W] markers of what the validator enforces |

## Persistence

Agent definitions live in the repo (`.agents/agents/<name>.toml`) and are reused across sessions — never recreate one per task; extend the existing definition when the scope partially matches.
