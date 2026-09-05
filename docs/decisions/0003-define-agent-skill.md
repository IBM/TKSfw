# ADR 0003 — Agent definition and naming move from AGENTS.md into the `define-agent` skill

Date: 2026-09-05 · Status: accepted

## Context
§ Agent Naming (~3.5 KB) and the agent-file field rules (~1.3 KB) were always-on in AGENTS.md but
are needed only when an agent is created or renamed. The role vocabulary was duplicated between
AGENTS.md and `[roles]` in `.agents/models.toml`. Nothing validated an agent file at write time; a
bad name surfaced only when the routing hook refused the spawn.

## Decision
| Choice | Rationale |
|---|---|
| Skill `define-agent` owns the whole procedure (fields + naming) | one owner, one reference (`references/naming.md`), Group-A: depends only on AGENTS.md L1/L2 and data from `models.toml` |
| `validate_agent.py` wired into `track_edits.py` for `.codex/agents/*.toml` | the same "content may leave the always-on file once a hook guarantees the outcome" argument that moved the ledger schemas |
| Vocabulary = keys of `[roles]`, minus `[naming] builtin_agents` | single source; the routing hook and the validator read the same table |
| AGENTS.md keeps a 3-bullet kernel + the load rule | pattern, reserved `main` and "rename is logged" are used at every delegation and every ledger entry, not only at creation |
| `sync --models` validates the rendered text | strip/inline re-renders are judged on their result; an invalid file is never mirrored to Claude Code |

## Consequences
- A non-conforming definition cannot persist unnoticed (write blocked; spawn still refused as second net).
- Warnings (short instructions, sandbox/tier mismatch, hand-written model in inline mode) are advisory.
- AGENTS.md headroom grows to ~14 KB under the 32 KiB cap.
