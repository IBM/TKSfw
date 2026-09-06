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
| `route_model.py` | `PreToolUse` (`^(Agent|Task)$\|spawn_agent`) | Reads `.agents/models.toml` at every spawn, resolves the agent's role → tier → model for the provider this session is connected to, and rewrites the spawn arguments (`updatedInput`: `model`, plus `reasoning_effort` on Codex). Unknown role or no routing table for the provider → the spawn is denied with the reason. `--print` shows the resolved table, `--check` validates the file. Decisions are journaled in `.hook-state/routing.jsonl`. Also enforces `[delegation]`: a spawn issued from inside a subagent (top-level `agent_id`/`agent_type`, Codex thread depth) is denied, and the (N+1)th live subagent (`max_parallel_agents`, default 4) is denied. |
| `subagent_track.py` | `SubagentStart` / `SubagentStop` | Maintains the set of live subagents in `.hook-state/subagents.json` for the parallel cap. A main-session Stop clears it, so a missed SubagentStop cannot wedge future spawns; entries also expire after 4 h. |
| `track_edits.py` | `PostToolUse` (all tools) | Hashes the watched set, journals the delta per tool call, validates changed ledgers against `.agents/skills/yaml-log-entry/references/schemas.md` and changed `.agents/agents/*.toml` against the `define-agent` validator (exit 2 = blocked with report); a valid agent source is then rendered to its harness mirrors, a deleted one prunes them (advisory `systemMessage` if rendering fails). Also runs `tasks_lint.py` on writes to the live `tasks.md`: syntactic findings (malformed line, unknown status, duplicate TaskID, checkbox/status mismatch) block with exit 2; missing evidence-of-closing is an advisory `systemMessage`. |
| `track_edits.py --phase prompt` | `UserPromptSubmit` | Journals edits made between turns as external, so the agent is not blamed for them. |
| `check_ledgers_on_stop.py` | `Stop` | Reads the journal for the turn; advisory `systemMessage` for un-logged deliverable/framework edits or delegations. `LEDGER_STOP_MODE=block` turns it into a continuation prompt. Also clears the live-subagent set and lists stale worktrees/work areas (task COMPLETED or branch merged) reported by the `delegate-work` skill's `workarea.py status`. |
| `refresh_state.py` | `Stop` | Regenerates `.agents/workarea/STATE.md`; prunes the journal. Adds an "Archivable plan blocks" hint when a fully COMPLETED block is followed by a newer one. |

## Arming (when the hooks act at all)

Every hook calls `hooklib.guard()` first and exits 0 silently — touching nothing — unless the project is
**armed**: `.agents/.tksfw.json` exists and its `enabled` is not `false`. `"enabled": false` disarms the
project on both harnesses (`tools/new_project.py <dir> --disable | --enable`), which is the per-project off
switch Codex does not offer for user-level hooks. Compatibility: an in-project layout (`.agents/hooks`)
without a manifest stays armed. A plugin instance running in a project that carries its own
`.agents/hooks/hooks.json` **yields** (the project pins its framework version; two layers would journal
twice). `inject_state.py` warns when the project manifest and the installed plugin differ in major.minor.

## Sessions, ownership and the lost-update guard (1.4.0)

- `inject_state.py` mints a **session token** (base62-8) per harness session (`.hook-state/sessions/<token>.json`: harness id, operator, heartbeat) and injects it with the operator name (configuration item `~/.config/tksfw/user.toml`, `name = "…"`, written by `new_project.py --set-operator`; `TKSFW_USER` overrides; `git config user.name` is a reported fallback). Every hook run refreshes the heartbeat; a second active session produces a warning at SessionStart.
- **Per-session snapshots** (`hashes.<token>.json`, `ids.<token>.json`): each session diffs against what *it* last saw, so nothing is swallowed by another session's hook run. Each change is attributed `own` (path named in the tool input, or a ledger entry with this session's `OwnerSessionId`), `external` (ledger entries owned by another session — never counted as unlogged, never a covering log entry) or `ambiguous` (unnamed edit while another session is active — treated as own, since reminders are advisory).
- **ID index** (`ids.json`): project-wide `{file: {hash, ids→owner}}` for ledgers and plans, refreshed whenever a file's hash differs from the last indexed one — independent of any session's diff, so an A-B-A rewrite that restores a byte-identical older file is still caught. `track_edits.py` blocks (exit 2, "LOST UPDATE") when an EntryID disappears from an append-only ledger, an entry owned by another session disappears from `decisions.yaml`/`deliverables.yaml`, or a TaskID leaves `tasks.md` without appearing in `tasks-archive.md`. New entries must carry `OwnerSessionId`/`OwnerSessionUserName` (validator `--require-owner`).
- Limits: the write has happened when PostToolUse runs — the block names what to restore, it cannot roll back. Shell edits under concurrency stay `ambiguous`. Sessions without the plugin are unattributed.

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
