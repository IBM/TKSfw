# ADR 0004 — Harness-neutral AGENTS.md: agent definitions move to `.agents/agents/`

Date: 2026-09-05 · Status: accepted

## Context
AGENTS.md still named Codex in four places: `.codex/agents/` as the agent-definition location,
"between Codex sessions", "Codex native task tools", and "Playwright/Perplexity skills" (MCP tools).
The same project is opened by both harnesses, so a per-harness rendered AGENTS.md is not an option.

## Decision
| Choice | Rationale |
|---|---|
| Neutral source `.agents/agents/<name>.toml`; `.codex/agents/*.toml` and `.claude/agents/*.md` become generated mirrors | same pattern as skills (`.agents/skills` → `.claude/skills`) and hooks (`hooks.json` → two harness files); AGENTS.md names only `.agents/**` |
| Mirrors excluded from the edit-hash watch set | one real edit → one reminder → one `changes.yaml` entry; drift is caught by `--check`, not by the ledger hook |
| Rendering by the PostToolUse hook after a clean validation (`agentlib.py`) | no manual step; works in plugin mode (the renderer travels with the hooks); a definition is usable by the other harness in the same turn |
| Rendering failures are advisory (`systemMessage`) | the write already happened; blocking would only hide the file |
| Neutral wording elsewhere ("the harness", "harness-native task tools (Codex `update_plan`, Claude Code `TaskCreate`)", "MCP tools") | hook event names stay: both harnesses share them |
| No templating of AGENTS.md | the harness is decided per session, not per project; two variants would drift and double the 32 KiB problem |

## Consequences
- Residual harness-specific files in a project: `CLAUDE.local.md` (`@AGENTS.md`) and `.codex/config.toml` — both harness-native by nature; everything else under `.codex/` and `.claude/` is generated.
- Existing projects: `git mv .codex/agents/*.toml .agents/agents/` then `sync_harness.py --models` once.
- `sync_harness.py --models` remains the bulk path after editing `models.toml`.
