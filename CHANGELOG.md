# Changelog

All notable changes to TKSfw. Format: Keep a Changelog; versions follow semver (`VERSION`).

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
