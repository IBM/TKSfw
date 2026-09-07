# Operational procedures

Each procedure names the command, when it takes effect and what to log. "Restart" means the harness
re-reads instruction files and hook registrations only at session start; everything else is live.

## Effect timing (reference)

| Layer | Read by | Effect of a change |
|---|---|---|
| `.agents/models.toml` (routing, pin, limits) | `route_model.py` at every spawn | Next spawn; the model is told at its next prompt |
| `.agents/.tksfw.json` `enabled` | `hooklib.guard()` at every hook run | Immediate |
| Operator (`user.toml`, `TKSFW_USER`) | SessionStart; `new_entry_id.py --stamp`; prompt notice | Next prompt (the model is told the new value) |
| Ledgers, `tasks.md`, archives | Hooks at their next run; STATE.md at turn end | Immediate; the model is told at its next prompt that files changed outside its tool calls |
| `AGENTS.md`, `CLAUDE.local.md`, skills, hooks, `.codex/config.toml` | Harness at startup | Next session; Codex re-trust when hook scripts changed |

The prompt notice is the UserPromptSubmit hook: it compares the configuration the model was shown with the
current one and injects one line per change, so `ks` can be used from another terminal — or by the model
itself through the shell tool — while a session is open.

## Procedures

| Procedure | Steps | Effect | Log |
|---|---|---|---|
| Switch model routing | `ks routing use <table>` (refuses while subagents run; `--force`) · `ks routing show` to verify | Next spawn | `changes.yaml`, Layer METHOD |
| Return to automatic routing | `ks routing use --clear` | Next spawn | METHOD |
| Change an operator name | `ks operator set "<name>"` | Next prompt | — |
| Disarm / re-arm a project | `ks project disable` / `enable` | Immediate (disarmed hooks cannot announce themselves) | METHOD |
| Update a project to the installed framework | 1. finish sessions (`ks project status` shows active ones) 2. `ks project update` (refuses while sessions are active; `--force`) 3. merge the files it lists as edited 4. restart the harness 5. Codex `/hooks` → trust 6. `ks harness retrust --ack` | Next session | METHOD |
| Upgrade the framework (user level) | 1. `git -C ~/tksfw pull` (or unzip the new bundle over `<home>`) 2. Codex `/plugins` → update tksfw; Claude `claude plugin update tksfw@tksfw` 3. `ks self version` 4. per project: "Update a project" above | Next session | — |
| Archive closed history | `ks ledger archive-plan` · `ks ledger archive <ledger|all> --before YYYY-MM-DD [--dry-run]` — safe during a session: the guard recognises the archive-first move, the model is told files changed | Immediate | `changes.yaml`, Layer PROJECT |
| Start over (new generation) | 1. finish sessions 2. commit 3. `ks project reset --dry-run` 4. `ks project reset --archive --label <phase> --yes` (or without `--archive` to clear; `--keep-agents` to reuse agent definitions) 5. commit. The next session announces "Generation N" and starts with empty ledgers and a fresh token; the previous generation is under `.agents/history/` | Immediate | first `changes.yaml` entry of the new generation (Layer PROJECT) |
| Before planning a phase or deciding | Read the "Ledger digest" in STATE.md (injected at start); `ks ledger digest` for the full view, `ks ledger digest --task <T>` for one task. To depart from an ACCEPTED decision: `events` entry `EventType: DECISION`, `DecisionID`, `Status: SUPERSEDED`, then the new decision | — | as described |
| Find a cross-reference | `ks ledger find <ID> --refs` | — | — |
| Export the ledgers to Excel (audit, review) | `ks ledger export all --archive` (or `ks ledger export changes,events`) → `.agents/workarea/exports/ledgers-<stamp>.xlsx`; `--csv DIR` for CSV | — | `events.yaml` AUDIT/TASK entry when the file is handed outside the project |
| Second session on the same project (same or another machine) | Ledgers are partitioned: each session writes `<ledger>.<token>.yaml`, reads all. SessionStart warns; STATE.md lists sessions; the prompt notice reports other sessions' entries. `tasks.md` has one plan-writer session per phase; others propose via an `events` TASK entry | — | — |
| Project folder on Box / Dropbox / OneDrive | Supported by design since 1.7.0: one writer per ledger file, per-host hook state. If the service still leaves a conflict copy (`changes (1).yaml`, `tasks (1).md`): `ks ledger check` fails and SessionStart/`ks doctor` name it — merge into the canonical file by hand, delete the copy, run `ks ledger check` | — | PROJECT |
| Fold legacy unsuffixed ledgers (pre-1.7.0 projects) | `ks ledger archive all --before <today>` when no session is open; the legacy files become empty/absent and every future entry lives in a shard | Immediate | PROJECT |
| Change a decision's status | Append an `events` entry: `EventType: DECISION`, `DecisionID: <id>`, new `Status` (`ACCEPTED`, `SUPERSEDED`, `DEPRECATED`) in your shard — never edit the decision entry | Immediate | — |
| Hooks changed (after an update) | Codex: open the project, `/hooks`, review, trust; then `ks harness retrust --ack`. Claude Code: nothing to trust | — | — |
| Check integrity | `ks ledger check` (validators, plan lint, cross-check incl. archives) · `ks doctor` | — | — |
| Clean isolation spaces after a phase | `ks project status` (counts) · `python3 .agents/skills/delegate-work/assets/workarea.py prune --stale` | — | — |

## Running `ks` from inside a session

The model may run `ks` through the harness shell tool (for example `ks routing use openrouter` when the
operator asks to switch providers). The change is a METHOD-layer change and must be logged; the hook
notice at the next prompt confirms what took effect.
