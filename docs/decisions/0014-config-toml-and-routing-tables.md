# ADR 0014 — `.agents/config.toml`, named routing tables with explicit provider match, `ks help`

Date: 2026-09-09 · Status: accepted · Version 3.0.0

## Context
`.agents/models.toml` had grown beyond model routing: `[hil]` (2.1.0), `[state]` (2.0.0), `[delegation]` (1.2.0)
live there too. The single routing table `[routing.ibm]` was selected by the coincidence that its key
equalled the Codex `model_provider` id, which made it impossible to keep two tables for one endpoint
(OpenAI and Anthropic models behind the same IBM provider). Discoverability of `ks` verbs relied on the
usage block and `docs/ks.md`.

## Decisions
| Choice | Rationale |
|---|---|
| Rename to `.agents/config.toml`; every reader accepts the legacy name; `ks project update` renames an existing file in place (content and recorded hash carried over) | The name now says what the file is; operators keep their pins, thresholds and limits |
| Tables are free names; Codex selection matches `match.codex_model_provider` first, then key == provider (legacy) | One endpoint, several model families |
| Shipped tables: `ibm-openai` (gpt-5.6-luna/terra/sol), `ibm-anthropic` (claude-haiku-4-5 / claude-sonnet-5 / claude-opus-5), `ibm-anthropic-cc` (1M-context variants for Claude Code), `openrouter` example | Operator's requirement; efforts stay low/medium/high |
| `ks routing list` prints the menu with match rule, models, pinned/active markers | Pinning needs a list to choose from |
| `ks help [<command>]` and `ks <command> --help` with a full guide per command, kept in `ks` itself | Productivity; one source that ships with the binary |
| Major version 3.0.0 | The file name and the table name are part of the 2.x compatibility promise (CHANGELOG 2.0.0); both change, with migration |

## Consequences
- `TKSFW_ROUTING=ibm` must become `ibm-openai`; a project's own pinned `selected = "ibm"` keeps working as long as its file still defines that table (an edited file is never overwritten).
- 8 new tests (272 total). Historical ADRs keep the old file name.
