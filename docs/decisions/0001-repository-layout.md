# ADR 0001 — Repository layout: template + generated dual-manifest plugin

Date: 2026-09-04 · Status: accepted

## Context
The framework was developed inside a Box-synced Codex project (`start-codex`). Box Drive ignores
symlinks, Codex re-trusts changed hooks per project, and neither plugin system ships instruction
files (`AGENTS.md`) or project-root configuration; both ship skills and hooks in the same layout.

## Decision
| Choice | Rationale |
|---|---|
| Repo outside Box, plain git, tagged releases | copier/git tooling needs a clean git template; Box adds nothing here |
| `template/` is the single source for the method instance | one place to edit; projects are instantiated by `tools/new_project.py` (stdlib, no symlinks) — works on Box |
| `plugins/tksfw/` is generated **and committed** | the repo root becomes a valid marketplace root for both harnesses without a build step on the consumer side; `build_plugin.py --check` in tests prevents drift |
| One plugin directory, two manifests | Codex requires `.codex-plugin/plugin.json`, Claude Code `.claude-plugin/plugin.json`; skills/ and hooks/ layouts are identical |
| Shared `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` | exported by Claude Code; Codex sets it too for compatibility |
| Two marketplace files | schemas differ (Codex: `policy`, `category`; Claude Code: `owner`) — writing both avoids validation surprises |
| `hooklib.py` resolves the project root from env/cwd | plugin scripts run from a cache dir; state must stay in the project |
| `sync_harness.py` excluded from the plugin | it only exists to mirror in-project hooks/skills into `.claude/`, which the plugin makes unnecessary |

## Consequences
- Full-mode projects keep working unchanged (legacy root resolution retained).
- Every METHOD change = version bump + rebuild + tag; Claude Code updates only on version change.
- Copier was not adopted for now: `new_project.py --update` covers refresh-unmodified / keep-edited
  with a hash manifest; copier can be layered on later if three-way merges become necessary.
