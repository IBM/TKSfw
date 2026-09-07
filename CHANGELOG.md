# Changelog

All notable changes to TKSfw. Format: Keep a Changelog; versions follow semver (`VERSION`).

## [1.7.1] — 2026-09-07

### Fixed
- Tool-input paths are matched against the project by real path (`hooklib._rel_input`): on macOS the harness reports `/var/folders/…` while the process cwd resolves to `/private/var/folders/…`, so "named in the tool call" never matched and the READ-ONLY LEDGER rule (foreign shard, legacy file) did not fire under two active sessions. Reproduced with a symlinked `TMPDIR`; the suite now passes in both spellings.

## [1.7.0] — 2026-09-07

Ledgers partitioned per session; per-host hook state — designed for project folders on Box/Dropbox/OneDrive.

### Added
- Session shards `<ledger>.<token>.yaml` for changes, lessons, handoffs, events, decisions: a session writes only its own shards; other shards and the unsuffixed legacy files are read-only (`track_edits.py` → exit 2 "READ-ONLY LEDGER"). All readers merge shards: STATE.md (`hooklib.load_kind`), `cross_check`, `find_entry`, `ks ledger check`, ID index, `archive_ledger` (archives every shard; emptied shards are removed; refuses while sessions are active unless `--force`).
- Decisions append-only: `Status` is the initial status; transitions are `events` of `EventType: DECISION` with the new optional `DecisionID` (validated, cross-checked); STATE.md computes the effective status.
- STATE.md "Sessions (ledger shards)" section; prompt notice "Session K (operator) added N entries: titles".
- `.hook-state/hosts/<hostname>/` for all mutable per-machine state (journal, snapshots, ID index, live subagents, routing journal, lock); `sessions/` stays shared. `TKSFW_HOST` override.
- Sync conflict-copy detection (`changes (1).yaml`, `tasks (conflicted copy).md`, …): SessionStart warning, STATE.md, `ks doctor` (FAIL), `ks ledger check` (fail). `ks doctor` also lists shards and legacy files.
- `new_entry_id.py --stamp` prints the target shard path. ADR 0010. 171 tests.

### Changed
- AGENTS.md § YAML-based Logs: partitioning/ownership rule; § Activity Plan: one plan, one writer session per phase (18,120 B). schemas.md, SKILL.md, hooks README, operations.md updated.
- `MUTABLE_LEDGERS` is now only `deliverables`.

## [1.6.0] — 2026-09-07

Live reconfiguration and a usable installation path.

### Added
- UserPromptSubmit notice (`track_edits.py --phase prompt`): "changed since your last prompt" — routing table/pin, operator, armed flag, `models.toml` edits, and files changed outside the session's tool calls (`ks`, another session, an editor). `hooklib.config_view/config_changes`; the SessionStart hook stores the view the model was shown. Both harnesses accept `additionalContext` on this event.
- `ks`: effect line after every mutating verb (next spawn / next prompt / next session / files); `routing use` refuses while subagents run and `project update` while sessions are active (`--force`); `ks self setup [--operator] [--no-stanza]` — one-shot idempotent user setup (operator, bootstrap stanzas appended to `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`, completion hint); `doctor` checks the stanzas and names the getting-started step for each WARN/FAIL.
- Docs: `docs/getting-started.md` (10 steps, both harnesses, uninstall), `docs/operations.md` (effect timing + procedures: switch routing, update, upgrade, archive, second session, re-trust, running `ks` from inside a session); README "Start here"; AGENTS.md § Tools line on `ks`; hooks README; ks.md "Effects and safety". 12 new tests (166 total).

## [1.5.1] — 2026-09-07

### Changed
- `plugin/` renamed to `plugin-src/` (hand-maintained plugin sources) to stop the one-letter confusion with the generated `plugins/`; `plugins/README.md` added ("GENERATED — do not edit here", with the source → output table); `build_plugin.py`, README, `docs/distribution.md` updated. No functional change.

## [1.5.0] — 2026-09-07

`ks` command line (P0) and cumulative ledger archives.

### Added
- `tools/ks` (stdlib Python, self-locating; shipped as `plugins/tksfw/bin/ks` with `ks-completion.sh`): `self install|version|home`, `operator set|show`, `project init|update|enable|disable|status|drift`, `routing show|check|resolve|use [--clear]`, `ledger check|find|archive-plan|archive`, `harness sync|retrust [--ack]`, `doctor`, `dev build|test|release`. `docs/ks.md`.
- `new_project.py --drift [--json]` (report-only), `route_model.py`: `selected = "<table>"` pin in `models.toml` (after `TKSFW_ROUTING`, before the provider match; validated).
- Archives: `.agents/workarea/archive/<ledger>.yaml` + `archive/tasks.md` (one cumulative, append-only archive per type); classes `archive:<kind>`/`plan-archive`; guard exemption generalised (archive-first move), archives never lose an ID; `cross_check` resolves into archives; `archive_ledger.py` (eligibility: closed history only; migrates `tasks-archive.md`).
- `find_entry.py <ID> [--refs|--prefix|--json]` — entries/tasks across live, archive and plan with reverse references.
- `~/.config/tksfw/trust.json` (hook-hash acknowledgement for `ks harness retrust`); `user.toml` gains `home`.
- ADR 0009; 26 new tests (154 total).

### Changed
- AGENTS.md § Activity Plan "keep it lean" line points to `archive/`; schemas.md § Archives; hooks README; README; user-level.md.

## [1.4.1] — 2026-09-06

The operator name becomes a defined configuration item.

### Added
- `~/.config/tksfw/user.toml` (`schema = 1`, `name = "…"`; directory overridable with `TKSFW_CONFIG_DIR`) as the canonical per-user item; `tools/new_project.py --set-operator "<name>"` writes it, `--show-operator` prints the resolved value and its source (exit 1 when unset); both available from `tksfw-init`.
- `hooklib.operator_source()`; SessionStart reports "(from git config — set it)" when only the fallback resolved. 6 new tests (128 total).

### Changed
- `TKSFW_USER` is documented as an override (CI, one-off shells), `git config user.name` as a reported fallback. Docs: user-level.md, schemas.md, hooks README, README, tksfw-init.

## [1.4.0] — 2026-09-06

Parallel sessions: session token, entry ownership, lost-update guard, session-keyed work areas.

### Added
- Session token (base62-8) minted per harness session by `inject_state.py`, injected with the operator name (`TKSFW_USER` → `~/.config/tksfw/user.toml` → `git config user.name`); heartbeat per hook run; warning when another session is active; records pruned after 24 h.
- Ledger schemas: `OwnerSessionId` / `OwnerSessionUserName` on all six files — required for new entries (`validate_yaml_log.py --require-owner`), accepted absent on legacy entries. `new_entry_id.py --stamp [--session]` prints a ready entry head.
- Lost-update guard in `track_edits.py` (exit 2): EntryID removed from an append-only ledger; another session's entry removed from `decisions.yaml`/`deliverables.yaml`; TaskID removed from `tasks.md` without appearing in `tasks-archive.md`. Project-wide ID index keyed by file hash — catches A-B-A rewrites.
- Per-session snapshots (`hashes.<token>.json`, `ids.<token>.json`) and change attribution `own | external | ambiguous`; external changes never count as unlogged nor as covering entries; Stop hook reports them.
- `workarea.py`: key `<session>.<task>.<instance>` (instance allocated atomically, `< max_parallel_agents`; `--instance` to reuse; `--session` required when several sessions are active); `prune --session`; worktrees use the same key.
- `subagent_track.py` / `route_model.py`: live-subagent cap per session; Stop clears only the own session.
- ADR 0008 (incl. queue evaluation); docs; 21 new repo tests (122 total), skill tests updated.

### Changed
- AGENTS.md: § YAML-based Logs ownership line; § Agent Work Areas key (16,514 → 17,043 B).

## [1.3.0] — 2026-09-06

Activity plan: rules stay in AGENTS.md; grammar and procedure move to `yaml-log-entry`; syntax is hook-enforced.

### Added
- `yaml-log-entry/references/tasks.md`: line grammar, evidence-of-closing rules with the terminal-positive pairs table, archive procedure, harness task-tool note. SKILL.md gains an "Activity plan" section; description covers `tasks.md`.
- `tasks_lint.py`: ERROR (malformed line, unknown status, duplicate TaskID, checkbox/status mismatch) vs WARN (evidence); exit 0/1/2; `--json`.
- `track_edits.py`: lints writes to the live `tasks.md` — errors block (exit 2) with the expected grammar, warnings are advisory; `tasks-archive.md` is never linted.
- `refresh_state.py`: "Archivable plan blocks" hint in STATE.md.
- ADR 0007; 9 new repo tests (101 total) + 1 skill fixture (`warn_tasks.md`).

### Changed
- AGENTS.md § Activity Plan reduced to five rules + pointer (17,715 → 16,514 B).

## [1.2.0] — 2026-09-06

Delegation: decision rules stay in AGENTS.md; mechanics move to a skill; the two limits become hook-enforced.

### Added
- `delegate-work` skill (Group A): `SKILL.md`, `references/isolation.md` (moved method text: worktree vs work area, handoff protocol, cleanup, changing models, persisting agent files), `assets/workarea.py` (`create <agent> <task> [--worktree]`, `list`, `prune <agent> <task> [--force]`, `prune --stale`, `status --json`), 11 skill tests.
- `subagent_track.py` on `SubagentStart`/`SubagentStop` (live-subagent set, cleared at main Stop, 4 h TTL).
- `route_model.py`: denies nested spawns and the (N+1)th live subagent; `[delegation] max_parallel_agents = 4`, `deny_nested_spawn = true` in `models.toml`.
- `check_ledgers_on_stop.py`: "Cleanup reminder" listing stale worktrees/work areas (task COMPLETED / branch merged).
- ADR 0006; 11 new repo tests (92 total).

### Changed
- AGENTS.md § Subagents: procedure lines replaced by pointers to `delegate-work`; § Agent Work Areas reduced to one line (17,998 → 17,715 B).
- `.agents/worktrees/` is never watched by the edit-hash hook.
- `define-agent` gains a Persistence note (moved from AGENTS.md).

## [1.1.0] — 2026-09-06

Install once per user, arm any project from the plugin.

### Added
- `tksfw-init` skill (plugin-only, `plugin/tksfw/skills/tksfw-init/`): the build bundles `template/`, `tools/new_project.py` and `VERSION` as skill assets, so a project can be created (`--plugin-mode` or self-contained), updated, disarmed or re-armed from the installed plugin without a repository checkout.
- Bootstrap stanzas `plugins/tksfw/bootstrap/AGENTS.global.md` (append to `~/.codex/AGENTS.md`) and `CLAUDE.global.md` (append to `~/.claude/CLAUDE.md`): method applies only where `.agents/.tksfw.json` is enabled; elsewhere inert; use `tksfw-init` when asked.
- `docs/user-level.md`; README and distribution updates; 6 new tests.

### Changed
- `tools/new_project.py` detects the skill-assets layout (`template/` next to the script).

## [1.0.0] — 2026-09-06

Safe for user-level deployment: the framework is inert unless a project is armed.

### Added
- `hooklib.armed()` / `guard()`: every hook (`inject_state`, `track_edits`, `check_ledgers_on_stop`, `refresh_state`, `route_model`) exits 0 before touching anything unless `.agents/.tksfw.json` exists with `enabled` ≠ false; legacy in-project layout without manifest stays armed; a plugin instance yields to a project with its own `.agents/hooks/hooks.json`.
- `resolve_project_root()` now reports how the root was found (`env | marker | legacy | cwd`); `cwd` means "no project" and is never armed.
- `inject_state.py`: version-skew warning (project manifest vs installed plugin, major.minor).
- `tools/new_project.py --disable | --enable`; manifest carries `enabled`.
- ADR 0005; hooks README § Arming; 12 new tests (unarmed folder, disabled project, yield, legacy, skew).

## [0.9.0] — 2026-09-05

AGENTS.md is harness-neutral; agent definitions get a neutral source and generated mirrors.

### Added
- `agentlib.py`: `.agents/agents/<name>.toml` → `.codex/agents/<name>.toml` (marker + routed model lines) and `.claude/agents/<name>.md`; managed mirrors (refresh, prune orphans, conflict on hand-made files); used by `track_edits.py` (render after a validated write, prune on delete, advisory `systemMessage` on failure) and by `sync_harness.py --models` (bulk).
- Template directory `.agents/agents/` (replaces `.codex/agents/.keep`).
- ADR 0004.

### Changed
- `AGENTS.md`: `.agents/agents/` replaces `.codex/agents/`; "between sessions, whichever harness"; "harness-native task tools (Codex `update_plan`, Claude Code `TaskCreate`)"; "Playwright/Perplexity MCP tools".
- `hooklib.py`: `AGENTS_SRC`, `AGENT_FILE_RE` → `.agents/agents/`, `MIRROR_PREFIXES` (`.claude/skills/`, `.codex/agents/`, `.claude/agents/`) never watched.
- `define-agent` skill and validator: source path `.agents/agents/`; mirrors are hook-rendered.
- `sync_harness.py --models` delegates to `agentlib`.

### Migration
- `git mv .codex/agents/*.toml .agents/agents/` in existing projects, then `python3 .agents/hooks/sync_harness.py --models`.

## [0.8.0] — 2026-09-05

Agent definitions become a skill-owned, validated procedure.

### Added
- `define-agent` skill: `SKILL.md` (procedure), `references/naming.md` (the former AGENTS.md § Subagents field rules + § Agent Naming, verbatim, with [E]/[W] markers), `assets/validate_agent.py` (name pattern, role ∈ `[roles]`, reserved `main`, harness built-ins refused, filename = name, description prefix, required fields, ≤ 3 tokens, sandbox-by-tier and content warnings, hand-written `model` error in strip mode), `tests/` (10 cases).
- `track_edits.py`: changed `.codex/agents/*.toml` are validated on write; errors block (exit 2) with a pointer to the skill.
- `sync_harness.py --models`: refuses to render an agent file whose rendered text fails validation (reported as conflict).
- `models.toml` `[naming] builtin_agents` (harness built-in names, excluded from the role vocabulary).
- `inject_state.py` preamble: "before creating or renaming any .codex/agents/*.toml, load the define-agent skill".

### Changed
- `AGENTS.md`: § Subagents field block and § Agent Naming reduced to a kernel (pattern, vocabulary = `[roles]` keys, reserved `main`, rename = logged change, load `define-agent`). 20,455 → 17,870 bytes.

## [0.7.0] — 2026-09-05

### Added
- `tksfw-tools` plugin (`plugin/tksfw-tools/` → `plugins/tksfw-tools/`): Perplexity (`@perplexity-ai/mcp-server`) and Playwright (`@playwright/mcp --isolated --output-dir <project>/.playwright`) MCP servers; per-harness definitions (`mcp/codex.json` with `env_vars`, `mcp/claude.json` with `userConfig` keychain option); `check_tools.py` SessionStart prerequisite check.
- Both marketplace catalogs list `tksfw` and `tksfw-tools`; `build_plugin.py` builds/checks/zips every plugin; `docs/mcp-tools.md`.

### Changed
- `plugin/` restructured per plugin (`plugin/tksfw/`, `plugin/tksfw-tools/`).

## [0.6.0] — 2026-09-05

Model selection becomes configuration: tiers in the method, provider tables in `.agents/models.toml`.

### Added
- `template/.agents/models.toml`: `[tiers]`, `[roles]`, `[routing.<provider>]` (ibm + openrouter example), `on_unknown_role`, `codex_agent_files`.
- `route_model.py` PreToolUse hook (`^(Agent|Task)$|spawn_agent`): per-spawn routing via `updatedInput` (`model`, Codex `reasoning_effort`), `additionalContext` with the routed model, deny on unknown role / missing table, `routing.jsonl` journal, `--print` / `--check` / `--resolve`.
- `sync_harness.py --models` (+ `--routing <key>`): renders `model`/`model_reasoning_effort` into `.codex/agents/*.toml` (`inline` or `strip`) and managed `.claude/agents/<name>.md` mirrors (model, effort, read-only tools).
- `inject_state.py`: one-line routing summary at SessionStart.
- `docs/model-routing.md`, ADR 0002; hooks README rows; tests for routing, rendering and mirrors.

### Changed
- `AGENTS.md` § Subagents: model rule rewritten in tier vocabulary; "judge tier" replaces the model name; models change only via `models.toml`.
- `hooklib.py`: `MODELS_TOML` constant.

## [0.5.0] — 2026-09-04

Initial import from the `start-codex` project (Box) into a versioned repository.

### Added
- `template/`: AGENTS.md (19.8 KB, schemas moved to the yaml-log-entry skill), CLAUDE.local.md, `.agents/hooks`, `.agents/skills` (4 Group-A skills), `.agents/workarea/.keep`, `.codex/` (config.toml, prompts, agents).
- Plugin build (`tools/build_plugin.py`) producing one plugin directory with both manifests (`.codex-plugin`, `.claude-plugin`), shared `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}`, and three ZIPs (+ SHA256SUMS).
- Marketplace catalogs at the repo root for Codex (`.agents/plugins/marketplace.json`) and Claude Code (`.claude-plugin/marketplace.json`).
- `tools/new_project.py`: full and `--plugin-mode` instantiation, hash-manifest based `--update`.
- `tests/run_tests.py`: 25 checks (skill suite, build, plugin-mode and in-project hook runs, update semantics, committed-plugin drift).

### Changed
- `hooklib.py`: project root resolved from `$TKSFW_PROJECT_ROOT` / `$CLAUDE_PROJECT_DIR` / walk-up from cwd / legacy file-relative; validator located next to the scripts (plugin) or in the project. Prerequisite for running the hooks from a plugin cache directory.
- `track_edits.py`, `check_ledgers_on_stop.py`: schema/asset paths in messages now come from `hooklib` instead of hard-coded `.agents/skills/...`.
