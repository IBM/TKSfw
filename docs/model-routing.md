# Model routing (`.agents/models.toml`)

Model IDs are configuration, not method. `AGENTS.md` speaks only in **tiers**; one file per project
maps tiers to the models of the provider the session is connected to; a hook applies the mapping at
every subagent spawn.

## Vocabulary

| Term | Meaning | Where it appears |
|---|---|---|
| tier | capability class: `research`, `build`, `judge` | `AGENTS.md`, `[tiers]`, `# tksfw-tier:` comments |
| role | the `-<role>` suffix of an agent name (`sources-researcher` → `researcher`) | `[roles]` → tier |
| routing | one `[routing.<key>]` table per provider: tier → `{ model, reasoning_effort }` | `models.toml` |

No word is shared with a harness setting: not `profile`, not `model_provider`. The file is read only
by `route_model.py` and `sync_harness.py`; Codex and Claude Code never open it.

## Selection of the routing table (at every spawn)

| Order | Source | Note |
|---|---|---|
| 1 | `$TKSFW_ROUTING=<key>` | operator override |
| 2 | Codex: `model_provider` in `$CODEX_HOME/config.toml` | the provider this session actually uses ([config reference](https://learn.chatgpt.com/docs/config-file/config-reference)) |
| 3 | Claude Code: `$ANTHROPIC_BASE_URL` starts with `match.claude_base_url` | gateway detection |
| 4 | `[routing.default]` | optional catch-all |
| — | none | spawn **denied** with the list of available tables |

## What happens at a spawn

| Harness | Hook input | Hook output (`permissionDecision: allow`, `updatedInput`) |
|---|---|---|
| Codex | `tool_name: spawn_agent` (alias `Agent`), agent from `agent_type` or the `task_name` prefix before `_` | original arguments + `model` + `reasoning_effort` ([Codex hooks](https://learn.chatgpt.com/docs/hooks): `updatedInput` replaces the arguments of local function tools) |
| Claude Code | `tool_name: Agent`, agent from `subagent_type` | original arguments + `model` — the per-invocation parameter, first in Claude Code's precedence ([subagents](https://code.claude.com/docs/en/sub-agents)); effort comes from the rendered `.claude/agents/*.md` frontmatter |

Both also receive `additionalContext` naming the model, so the orchestrator records `Model:` in the
Handoff/Event ledgers from fact; every decision is appended to `.hook-state/routing.jsonl`.

Refusals: unknown role (`on_unknown_role = "deny"`, or `"inherit"` to let the child inherit the
parent's model), no routing table for the provider, unparsable `models.toml`.

## Agent definition files

The source is harness-neutral: `.agents/agents/<name>.toml` (same TOML fields Codex documents). The
hooks (`agentlib.py`, called by `track_edits.py` after every validated write and by
`sync_harness.py --models` in bulk) determine the tier (`# tksfw-tier:` comment, else the name's
role) and render two managed mirrors:

| Mirror | Rendering |
|---|---|
| `.codex/agents/<name>.toml` | source text + marker line; `codex_agent_files = "inline"` (default): `model` and `model_reasoning_effort` from the tier — Codex documents that a value set in the agent file takes precedence over the spawn value, so mirror and hook always agree. `"strip"`: no model lines, the hook is the only source |
| `.claude/agents/<name>.md` | `name`, `description`, `model`, `effort` (Codex → Claude vocabulary), `tools` restricted for `sandbox_mode = "read-only"`, body = `developer_instructions`. Claude Code hot-reloads this directory |

Mirrors are never watched by the edit-hash hook (only the source is a framework edit); a hand-made
file at a mirror path is reported as a conflict and never touched; deleting a source prunes its mirrors.

## Changing models mid-session

1. Wait for running subagents to finish.
2. Edit `.agents/models.toml` (the hash hook journals this as a METHOD edit → `changes.yaml`).
3. `python3 .agents/hooks/sync_harness.py --models` to re-render every agent mirror with the new
   models (in plugin-mode projects, re-save each `.agents/agents/*.toml` instead — the hook renders).
4. Next spawn uses the new mapping. No restart; the hook **script** is unchanged, so Codex needs no
   `/hooks` re-trust.

Switching **provider** is not a mid-session operation in either harness (Codex: `model_provider` is
user-level and inherited by children; Claude Code: one `ANTHROPIC_BASE_URL` per process). Relaunch
with the other provider; the matching `[routing.<key>]` table is selected automatically.

## Constraints on model IDs

| Harness | Rule |
|---|---|
| Codex | free string, sent as-is; the provider must speak the Responses API (`wire_api = "responses"` is the only value); every tier in a table must exist on that single endpoint |
| Claude Code | behind a gateway / custom base URL "Claude Code passes any string through without checking it" ([model config](https://code.claude.com/docs/en/model-config)); on the Anthropic API names must be recognised; enterprise `availableModels` also applies to subagent models |
| Effort | Codex `minimal/low/medium/high/xhigh`; Claude Code `low/medium/high/xhigh/max`; `--check` validates the vocabulary, the provider validates support per model |

## Verification checklist (per provider, once)

| Check | How |
|---|---|
| Table resolves | `python3 .agents/hooks/route_model.py --print` at the project root |
| File valid | `python3 .agents/hooks/route_model.py --check` |
| Codex honours the injected model | spawn a `*-researcher` probe, then compare `routing.jsonl` with the child's `turn_context.payload.model` in `~/.codex/sessions/` |
| Claude Code honours it | spawn a probe; the transcript's Agent call shows `model`; `/agents` lists the mirrors |
| `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` unset | when set, Claude Code ignores per-invocation and frontmatter models |
