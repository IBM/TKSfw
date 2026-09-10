# ADR 0015 — Session-scoped routing, session identity from a shell

Date: 2026-09-10 · Status: accepted · Version 3.4.0

## Context
`ks routing use` pinned the table in `.agents/config.toml`; every session of the project switched at its next
spawn and learnt it only afterwards. In a shared (Box) project with two operators this is an unsafe default.
A session-scoped switch needs (a) a per-session store the hook can read and (b) a way for `ks`, which runs in a
shell, to know which session it is acting for.

## Decisions
| Choice | Rationale |
|---|---|
| Override stored as `routing` in the session record (`.hook-state/sessions/<token>.json`) | Already per session, already shared across hosts, archived with the session — no cleanup |
| Selection order: session override → `TKSFW_ROUTING` → `selected` → provider match → URL match → `default_routing` | Narrowest and most recent operator act wins; a session can escape a shell-profile variable |
| Project-wide switch refuses while other sessions are active unless `--force`, listing them | Same guard family as `project update`, `reset`, `archive`; the side effect becomes deliberate |
| Session identity: `$TKSFW_SESSION` exported by the SessionStart hook via `CLAUDE_ENV_FILE` → unique active session on this host by this operator → error listing candidates | Exact where the harness allows (Claude Code); in Codex the model passes its token; humans in a terminal get a safe heuristic |
| Session records carry `host` | Needed for the heuristic and for the sessions table |
| `ks project status` prints a sessions table with a "this session" / "probably yours" marker | The operator must see the token before typing it |
| Session switch does not touch `.claude/settings.local.json` / `.codex/config.toml` or the agent mirrors | Those are project-wide launch defaults |
| Claude Code limitation accepted and printed: custom agents keep the frontmatter model; built-ins follow via alias; `TKSFW_ROUTING=<table> claude` for an exact fresh session | The alternative (frontmatter without model) would couple sessions again |

## Consequences
- 16 new tests (298 total). Hooks: `select_routing(table, harness, payload=None, session_override=None)`; `route_model.py --print/--main/--resolve --session-routing <table>`.
