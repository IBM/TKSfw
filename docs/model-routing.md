# Model routing (`.agents/config.toml`)

Model IDs are configuration, not method. `AGENTS.md` speaks only in **tiers**; one file per project
maps tiers to the models of the provider the session is connected to; a hook applies the mapping at
every subagent spawn.

## Vocabulary

| Term | Meaning | Where it appears |
|---|---|---|
| tier | capability class: `research`, `build`, `judge` | `AGENTS.md`, `[tiers]`, `# tksfw-tier:` comments |
| role | the `-<role>` suffix of an agent name (`sources-researcher` → `researcher`) | `[roles]` → tier |
| routing | one `[routing.<key>]` table per provider: tier → `{ model, reasoning_effort }` | `config.toml` |

No word is shared with a harness setting: not `profile`, not `model_provider`. The file is read only
by `route_model.py` and `sync_harness.py`; Codex and Claude Code never open it.

## Selection of the routing table (at every spawn)

| Order | Source | Note |
|---|---|---|
| 0 | session override (`ks routing use <table> --session [token]`) | one session only; stored in its record under `.hook-state/sessions/`, dies with the session (3.4.0) |
| 1 | `$TKSFW_ROUTING=<table>` | operator override for one shell (launch time) |
| 2 | `selected = "<table>"` in `config.toml` | `ks routing use <table>`; `ks routing use --clear` unpins |
| 3 | Codex: `model_provider` in `$CODEX_HOME/config.toml` | the **first table in file order** whose `match.codex_model_provider` equals it, else a table keyed by it ([config reference](https://developers.openai.com/codex/config-reference)) |
| 4 | Claude Code: `$ANTHROPIC_BASE_URL` starts with `match.claude_base_url` | gateway detection |
| 5 | `default_routing = "<table>"` (top of `config.toml`) | the named default — `ibm-anthropic-cc` in the template, because Claude Code is the preferred harness |
| 6 | `[routing.default]` | legacy catch-all table |
| — | none | spawn **denied** with the list of available tables |

`ks routing list` prints every table with its match rule and models and marks the pinned and the active one.

## Tables shipped in the template (3.1.0)

Preferred harness: **Claude Code**. The IBM endpoint is one Codex provider (`model_provider = "ibm"`) for both model families.

| Table | Harness | research | build | judge | Selected by |
|---|---|---|---|---|---|
| `ibm-anthropic-cc` | Claude Code — **default** | claude-haiku-4-5 | claude-sonnet-5[1m] | claude-opus-5[1m] | `default_routing` (any Claude Code session without a gateway match) |
| `ibm-openai-cc` | Claude Code | gpt-5.6-luna[1m] | gpt-5.6-terra[1m] | gpt-5.6-sol[1m] | `ks routing use ibm-openai-cc` (or `TKSFW_ROUTING`) |
| `ibm-anthropic` | Codex | claude-haiku-4-5 | claude-sonnet-5 | claude-opus-5 | `match.codex_model_provider = "ibm"` — listed first, so it wins the provider match |
| `ibm-openai` | Codex | gpt-5.6-luna | gpt-5.6-terra | gpt-5.6-sol | same match rule, listed second → `ks routing use ibm-openai` (or `TKSFW_ROUTING=ibm-openai`) to use it |
| `openrouter` | Claude Code via gateway (example) | google/gemini-flash-latest | anthropic/claude-sonnet-latest | anthropic/claude-opus-latest | `match.claude_base_url = "https://openrouter.ai/api"` |

Before 3.0.0 the only IBM table was `[routing.ibm]`, selected because its key equalled the provider id. `TKSFW_ROUTING=ibm` in a shell profile must become one of the names above.

## What happens at a spawn

| Harness | Hook input | Hook output (`permissionDecision: allow`, `updatedInput`) |
|---|---|---|
| Codex | `tool_name: spawn_agent` (alias `Agent`), agent from `agent_type` or the `task_name` prefix before `_` | original arguments + `model` + `reasoning_effort` ([Codex hooks](https://learn.chatgpt.com/docs/hooks): `updatedInput` replaces the arguments of local function tools) |
| Claude Code | `tool_name: Agent`, agent from `subagent_type` | original arguments + `model` — the per-invocation parameter, first in Claude Code's precedence ([subagents](https://code.claude.com/docs/en/sub-agents)); effort comes from the rendered `.claude/agents/*.md` frontmatter |

Both also receive `additionalContext` naming the model, so the orchestrator records `Model:` in the
Handoff/Event ledgers from fact; every decision is appended to `.hook-state/routing.jsonl`.

Refusals: unknown role (`on_unknown_role = "deny"`, or `"inherit"` to let the child inherit the
parent's model), no routing table for the provider, unparsable `config.toml`.

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

## Project-wide vs session-scoped switching (3.4.0)

| | `ks routing use <table>` | `ks routing use <table> --session [token]` |
|---|---|---|
| Scope | every session of the project, at its next spawn | one session, at its next spawn |
| Storage | `selected` in `.agents/config.toml` | `routing` in that session's record |
| Guard | refuses while other sessions are active or agents are live; `--force` switches them all | none needed |
| Notice | every other session: "Model routing now X — was Y" | that session only: "… via session override — THIS SESSION ONLY" |
| Main-session model | written to `.claude/settings.local.json` / `.codex/config.toml` for the next launch, `/model` line printed | `/model` line printed; launch defaults untouched |
| Claude Code custom agents | mirrors re-rendered with the new ids | keep the project-wide frontmatter model (the spawn alias cannot override frontmatter); built-ins follow via alias. For an exact session launch with `TKSFW_ROUTING=<table> claude` |

How `--session` without a token finds yours: `$TKSFW_SESSION` — exported into every Bash-tool command of a Claude Code session by the SessionStart hook through `CLAUDE_ENV_FILE` ([Claude Code hooks](https://code.claude.com/docs/en/hooks)) — then the only active session on this host by this operator, otherwise the candidates are listed. In Codex the model passes its own token (shown in the SessionStart block); `ks project status` prints the sessions table.

## The main session's model (3.2.0)

The routing tables govern subagent spawns through the hook. The **main session** (the orchestrator, which
plans and judges) is launched by the harness with its own model choice, so TKSfw aligns it to the **judge
tier** of the active table where each harness reads its startup model:

| Harness | Written by `ks project init|update` and `ks routing use` | When it applies |
|---|---|---|
| Claude Code | `.claude/settings.local.json` → `"model"` (project-local, wins over the user default; not template-managed) | next launch; now: `/model <judge model>` (`s` in the picker = this session only) |
| Codex | `.codex/config.toml` → `model`, `model_reasoning_effort` (project config; `ks project update` keeps these lines) | next launch; now: `/model` |

Neither harness re-reads settings during a session, so `ks routing use` prints the `/model` command to run,
and the prompt notice tells the model to ask the operator for it. `python3 .agents/hooks/route_model.py --main`
prints the resolved main-session model per harness.

A pinned table applies to both harnesses: pin a `-cc` table only in projects you run with Claude Code (Codex
would be handed `…[1m]` ids). Unpinned, the selection is harness-aware (provider match for Codex,
`default_routing` for Claude Code).

## Claude Code and third-party model ids (3.3.0)

Claude Code's Agent tool accepts only the aliases `sonnet`, `opus`, `haiku`, `fable` in its per-spawn `model`
parameter, while agent frontmatter, `/model`, `--model` and the `ANTHROPIC_DEFAULT_<ALIAS>_MODEL` variables
accept full ids ([model configuration](https://code.claude.com/docs/en/model-config),
[subagents](https://code.claude.com/docs/en/sub-agents)). TKSfw therefore uses three channels together:

| Channel | Content | Written by |
|---|---|---|
| Spawn (`updatedInput.model`) | the tier's **alias**: research → `haiku`, build → `sonnet`, judge → `opus` (override: `[claude_aliases]` in `config.toml`, `tier = "alias"`) | `route_model.py` at every spawn |
| Alias map (`env` in `.claude/settings.local.json`) | `ANTHROPIC_DEFAULT_HAIKU_MODEL` / `SONNET` / `OPUS` = the table's research / build / judge ids — this is how a gateway model such as `gpt-5.6-terra[1m]` is reached through an alias | `ks routing use`, `ks project init|update`; applies at the next launch |
| Custom agent frontmatter (`.claude/agents/<name>.md`) | `model: <full routed id>` — takes precedence over the alias, so custom agents are exact even before a restart | the hook on every agent write; `ks routing use` re-renders all mirrors |

Built-in agent types (`Explore`, `Plan`, `general-purpose`) have no frontmatter and rely on the alias map, so
**restart Claude Code after `ks routing use`** for them to follow. The hook's `additionalContext` always names
the concrete id ("spawned as alias `sonnet` → gpt-5.6-terra[1m] via ANTHROPIC_DEFAULT_SONNET_MODEL") and the
ledger entries record that id. Anthropic states it does not support routing Claude Code to non-Claude models
through gateways ([LLM gateway](https://code.claude.com/docs/en/llm-gateway)); the mechanism above is the
documented alias-override path, and it works as far as the gateway accepts the ids.

`.agents/agents/<name>.toml` is the harness-neutral **source** of an agent definition (ADR 0004), not a Codex
file: `.codex/agents/<name>.toml` and `.claude/agents/<name>.md` are generated from it.

## Changing models mid-session

1. Wait for running subagents to finish.
2. Edit `.agents/config.toml` (the hash hook journals this as a CORE-layer edit → `changes.yaml`).
3. `python3 .agents/hooks/sync_harness.py --models` to re-render every agent mirror with the new
   models (in plugin-mode projects, re-save each `.agents/agents/*.toml` instead — the hook renders).
4. Next spawn uses the new mapping. No restart; the hook **script** is unchanged, so Codex needs no
   `/hooks` re-trust.

Switching **provider** is not a mid-session operation in either harness (Codex: `model_provider` is
user-level and inherited by children; Claude Code: one `ANTHROPIC_BASE_URL` per process). Relaunch
with the other provider; the matching `[routing.<key>]` table is selected automatically.

## Delegation limits (same file, `[delegation]`)

| Key | Default | Enforced by |
|---|---|---|
| `max_parallel_agents` | 4 | `route_model.py` denies the (N+1)th spawn while N subagents of THIS session are live (`subagent_track.py` on SubagentStart/Stop; per session since 1.4.0); also bounds work-area instance numbers |
| `deny_nested_spawn` | true | `route_model.py` denies a spawn whose hook payload shows a subagent context (Claude Code top-level `agent_id`/`agent_type`; Codex thread path depth ≥ 1). Set to false if a harness ever reports these fields for the main session |

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
