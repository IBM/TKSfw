# ADR 0002 — Model selection as configuration (tier routing)

Date: 2026-09-05 · Status: accepted

## Context
`AGENTS.md` named provider-specific model IDs (`gpt-5.6-luna/terra/sol`) in the Subagents rules and
the same IDs were repeated in every `.codex/agents/*.toml`. The framework is used against several
third-party providers, and the operator wants to change the mapping mid-session.

## Decision
| Choice | Rationale |
|---|---|
| Method text uses tiers (`research`, `build`, `judge`), never model IDs | provider-neutral; the naming vocabulary (`-<role>`) already encodes the tier |
| One file `.agents/models.toml`: `[tiers]`, `[roles]`, `[routing.<provider>]` | single source; keyed by the id the harness already knows (`model_provider`, base URL) so selection is automatic |
| Vocabulary avoids `profile` / `model_provider` | those words belong to Codex; project-scoped `.codex/config.toml` ignores them anyway |
| `route_model.py` PreToolUse hook rewrites the spawn (`updatedInput`) | per-invocation model is the top of both harnesses' precedence; the table is re-read per spawn so edits apply without restart or re-trust |
| `sync_harness.py --models` renders agent files too (`inline` default) | Codex documents that the agent file's `model` beats the spawn value — rendering both from one table removes the disagreement; Claude mirrors get `model`+`effort`, hot-reloaded |
| Unknown role / no table → deny | fail loud: silently inheriting the parent model was the observed failure mode |
| Every tier carries `reasoning_effort` | omitted effort resolves differently per harness (model default vs session effort) |

## Consequences
- Provider switch = relaunch with another provider; model switch within a provider = edit + `--models`.
- Whether Codex honours `updatedInput.model` on `spawn_agent` is documented only generically; the
  verification checklist in `docs/model-routing.md` must be run once per Codex upgrade.
- All models in one table must be served by the session's single endpoint (aggregators such as
  OpenRouter make mixed vendors possible).
