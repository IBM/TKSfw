# Changelog

All notable changes to TKSfw. Format: Keep a Changelog; versions follow semver (`VERSION`).

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
