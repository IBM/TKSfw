# Project hooks (harness-neutral: Codex CLI + Claude Code)

Single implementation, run unchanged by both harnesses. Hook commands are relative to the
project root (launch the harness there); every other path is resolved by the scripts from their
own location, so `cwd` never matters.

| File | Event | Purpose |
|---|---|---|
| `hooks.json` | — | Single source of the hook config. Edit here, then `python3 .agents/hooks/sync_harness.py`. |
| `agentlib.py` | — | Agent definitions: `.agents/agents/<name>.toml` (neutral source) → `.codex/agents/<name>.toml` (Codex mirror with the routed model lines) + `.claude/agents/<name>.md` (Claude Code mirror). Managed by marker; hand-made files at mirror paths are conflicts; orphans removed. Called by `track_edits.py` after each validated write and by `sync_harness.py --models`. |
| `sync_harness.py` | — | `--models`: bulk re-render of all agent mirrors (after editing `models.toml`) via `agentlib`. Mirrors `hooks.json` → `.codex/hooks.json` (verbatim) and → `hooks` key of `.claude/settings.json`; mirrors every `.agents/skills/<name>` into `.claude/skills/<name>` — per-skill relative symlink, or a managed copy with a `.mirror.json` marker where symlinks do not sync (Box Drive; `--mode auto` detects `~/Library/CloudStorage/`). Orphan mirrors are removed; hand-made directories are never touched. `--check` reports drift; `--hooks` / `--skills` restrict scope. |
| `hooklib.py` | — | Shared helpers: payload normalization (`turn_id`/`prompt_id`), hashing, journal, lock, ledger parsing via `yaml-log-entry`. |
| `inject_state.py` | `SessionStart` (`startup\|resume\|clear\|compact\|fork`) | Re-baselines the hash state, regenerates `STATE.md`, injects it as `additionalContext` (capped at 9,000 chars). |
| `route_model.py` | `PreToolUse` (`^(Agent|Task)$\|spawn_agent`) | Reads `.agents/models.toml` at every spawn, resolves the agent's role → tier → model for the provider this session is connected to, and rewrites the spawn arguments (`updatedInput`: `model`, plus `reasoning_effort` on Codex). Unknown role or no routing table for the provider → the spawn is denied with the reason. `--print` shows the resolved table, `--check` validates the file. Decisions are journaled in `.hook-state/routing.jsonl`. |
| `track_edits.py` | `PostToolUse` (all tools) | Hashes the watched set, journals the delta per tool call, validates changed ledgers against `.agents/skills/yaml-log-entry/references/schemas.md` and changed `.agents/agents/*.toml` against the `define-agent` validator (exit 2 = blocked with report); a valid agent source is then rendered to its harness mirrors, a deleted one prunes them (advisory `systemMessage` if rendering fails). |
| `track_edits.py --phase prompt` | `UserPromptSubmit` | Journals edits made between turns as external, so the agent is not blamed for them. |
| `check_ledgers_on_stop.py` | `Stop` | Reads the journal for the turn; advisory `systemMessage` for un-logged deliverable/framework edits or delegations. `LEDGER_STOP_MODE=block` turns it into a continuation prompt. |
| `refresh_state.py` | `Stop` | Regenerates `.agents/workarea/STATE.md`; prunes the journal. |

## Watched set (what hashing covers)

| Class | Paths | Rule |
|---|---|---|
| `ledger:*` | `.agents/workarea/{changes,lessons,handoffs,events,decisions,deliverables}.yaml` | Validated on change; `changes/handoffs/events` writes clear the corresponding reminder |
| `plan` | `.agents/workarea/tasks*.md` | Tracked, never loggable |
| `deliverable` | Globs from `deliverables.yaml` (`Path`) | Edit after last `changes.yaml` write → reminder |
| `framework` | `.agents/**` (incl. `.agents/agents/*.toml`, `.agents/models.toml`), `.codex/**`, `.claude/**` (minus workarea and mirrors), `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `MISSION.md`, `Job Role Definitions.md` | Same rule, Layer METHOD/ARCHETYPE |

Never watched: `STATE.md`, `.agents/workarea/.hook-state/**`, the generated mirrors `.claude/skills/**`, `.codex/agents/**`, `.claude/agents/**`, agent work areas
(`.agents/workarea/<agent>/…`), `__pycache__`, `.DS_Store`, `.obsidian`, `.claudian`.

Runtime state lives in `.agents/workarea/.hook-state/`: `hashes.json` (last baseline),
`journal.jsonl` (one line per tool call that changed something, plus `stop` markers),
`routing.jsonl` (one line per subagent spawn: agent, tier, model, routing table),
`hooks.log` (internal errors; hooks are fail-open and never wedge a turn).

## Model routing (`.agents/models.toml`)

Tiers (`research`, `build`, `judge`) are the only model vocabulary in AGENTS.md; one
`[routing.<provider>]` table per provider maps tiers to model IDs + reasoning effort. Table
selection at spawn time: `$TKSFW_ROUTING` → Codex `model_provider` (`$CODEX_HOME/config.toml`) →
Claude `$ANTHROPIC_BASE_URL` prefix (`match.claude_base_url`) → `[routing.default]` → deny.
Changing models mid-session: wait for running agents, edit `models.toml`, run
`sync_harness.py --models`; the next spawn uses the new mapping (the hook script is unchanged,
so Codex needs no `/hooks` re-trust). All models in a table must be served by the single provider
the session is connected to — neither harness lets a subagent use a different provider.

## Operations

- Codex trusts hooks by hash: after any change to `hooks.json`, run `sync_harness.py`, then open
  `/hooks` in Codex and re-trust. Until then the changed hooks are silently skipped.
- Project-local hooks load only once the project `.codex/` layer is trusted (first launch prompt).
- Claude Code reads `.claude/settings.json` directly; no trust step for hooks.
- Both harnesses run matching hooks in parallel; the scripts serialize through
  `.hook-state/.lock`, so concurrent tool calls are journaled once each.
- Standalone use: `python3 .agents/hooks/refresh_state.py --print`,
  `python3 .agents/hooks/sync_harness.py --check`.
- Adding or editing a skill: work in `.agents/skills/<name>/`, then run `sync_harness.py` — Codex
  reads the source natively, Claude Code reads the mirror. In copy mode, edit the source, never
  the mirror (`--check` flags drift). Instruction files (`CLAUDE.local.md`,
  `AGENTS.md`) are never generated by these scripts.
