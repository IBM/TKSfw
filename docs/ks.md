# `ks` — the TKSfw command line

One front door for every framework operation. `ks` is a stdlib-only Python script (the hooks already
require Python ≥ 3.11) that resolves *where* the framework and the project are and dispatches to the
existing scripts; it adds only the status, drift, doctor and re-trust views.

## Install

| Step | Command |
|---|---|
| From a checkout | `python3 tools/ks self install` → symlink `~/.local/bin/ks`, records `home` in `~/.config/tksfw/user.toml` |
| From the plugin | `python3 <plugin root>/bin/ks self install` (same effect; home = the plugin bundle) |
| Completion (zsh/bash) | `source <home>/tools/ks-completion.sh` (checkout) or `<plugin>/bin/ks-completion.sh` |
| Verify | `ks self version` · `ks doctor` |

Home resolution: `TKSFW_HOME` → `home` in `user.toml` → the script's own location → harness plugin
directories. Project resolution: `TKSFW_PROJECT_ROOT` → nearest ancestor of cwd with `.agents/.tksfw.json`.
In a full-mode project the in-project hooks and skills (the pinned version) are used; otherwise the home's.

## Commands

| Command | Does | Backed by |
|---|---|---|
| `ks self install [--bin-dir D]` / `version` / `home` | PATH symlink + home record; versions | — |
| `ks self setup [--operator NAME] [--no-stanza]` | one-shot, idempotent user setup: operator, bootstrap stanzas appended to `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`, completion hint | — |
| `ks operator set "<name>"` / `show` | per-user `~/.config/tksfw/user.toml` (`OwnerSessionUserName`) | `new_project.py --set/--show-operator` |
| `ks project init [dir] [--full]` | instantiate the method (plugin mode by default) | `new_project.py [--plugin-mode]` |
| `ks project update [dir]` | refresh unmodified framework files, list edited ones | `new_project.py --update` |
| `ks project enable` / `disable` | arm / disarm (`.agents/.tksfw.json` `enabled`) | `new_project.py --enable/--disable` |
| `ks project status` | version vs installed, mode, armed, drift counts, the sessions table (token, harness, operator, host, started, last seen, routing; "← this session" / "← probably yours"), project layers, plan focus, isolation spaces | manifest, `--drift --json`, `.hook-state/sessions/`, STATE.md, `workarea.py status` |
| `ks project sessions [list]` | the sessions table alone, with the count of sessions ended in the last 3 h | `.hook-state/sessions/` |
| `ks project sessions close <token>… \| --stale \| --all` | mark records ended by hand — for a harness that quit without firing `SessionEnd` (plugin older than 3.5.0, crash). `--stale`: heartbeat older than 30 min. Ended records stop counting as active at once, so `update`, `reset`, `routing use` no longer need `--force` | writes `ended` into the record |

**What "active" means (3.5.0).** A session record is active while it has not been ended and its heartbeat (every prompt and tool call) is younger than 30 minutes. Both harnesses fire a `SessionEnd` hook when the main thread closes ([Codex](https://developers.openai.com/codex/hooks): close, archive, or 30 min idle; [Claude Code](https://code.claude.com/docs/en/hooks): exit, `/clear`, `/resume`, logout) — the framework marks the record ended there, so a closed session disappears from the active count immediately. A record still listed after you closed the harness means the hook did not fire; `ks project sessions close` fixes it. `/resume` of an ended session reopens its record.
| `ks project drift [--json]` | unchanged / outdated / edited / missing per file; exit 1 on drift; writes nothing | `new_project.py --drift` |
| `ks project reset [--archive [--label L]] [--keep-agents] [--registry] [--dry-run] [--yes] [--force]` | start over: clears ledgers (all shards + legacy), archives, `tasks.md`, STATE.md, exports, hook state (all hosts), work areas, worktrees, agent definitions + mirrors. `--archive` moves ledgers/plan/archives/exports/work areas/agents to `.agents/history/<stamp>[-label]/` instead (hook state is always deleted; worktree branches kept). Registry kept unless `--registry`; agents kept with `--keep-agents`. Refuses while sessions are active, without `--yes` (non-interactive) or with unmerged worktree branches (`--force`). Records the generation in `.agents/.tksfw.json` → SessionStart and STATE.md announce "Generation N" | — |
| `ks routing list` | every routing table with match rule, models per tier, pinned/active markers — the menu for `ks routing use` | `config.toml` |
| `ks routing show` / `check` / `resolve <agent>` | resolved table, validation, one agent's model | `route_model.py --print/--check/--resolve` |
| `ks routing use <table>` / `use --clear` | pin a routing table (`selected = "<table>"` in `config.toml`, read after `TKSFW_ROUTING`, before the provider match) | edits `config.toml`, then `--check` |
| `ks hil show` | effective Human-in-the-Loop threshold (`[hil]` in `config.toml`) | — |
| `ks hil set [--impact L] [--reversibility L] [--logic and\|or] [--mode enforce\|advisory]` | change the threshold live: validated, `[hil]` rewritten in place, effect line; the session is told at its next prompt | — |
| `ks layers resolve [--archetype P] [--spec P] [--json]` | where the project layers (ARCHETYPE `KS_PROJECT.md`, PROJECT spec `KS_SPEC.md`) are and their status: `KS_PROJECT.md` / `KS_SPEC.md` at the root (convention), paths pinned in `.agents/.tksfw.json` `layers`, or the arguments (win per key); `new` / `unchanged` / `changed` (re-read) / `missing` (declared but absent). Exit 0 resolved, 3 nothing, 4 missing | `layers.py` |
| `ks layers pin --archetype P \| --spec P` / `pin --clear` | declare non-conventional paths (relative, inside the project, `.md`; either key alone) / return to the convention; refuses while subagents run | edits `.agents/.tksfw.json` |
| `ks layers journal` | record the current layer hashes — the baseline the next SessionStart compares against (the hook and the `ks-start` skill do this too) | `.hook-state/hosts/<host>/layers.json` |
| `ks layers section` | print the pointer block the SessionStart hook injects | `layers.py` |
| `ks ledger check` | validate every live ledger and archive, lint `tasks.md`, cross-check FKs | `validate_yaml_log.py`, `tasks_lint.py`, `cross_check.py` |
| `ks ledger find <id> [--refs] [--json]` / `find --prefix <chars>` | locate an entry or task across live files, archives and plan; `--refs` lists everything that references it | `find_entry.py` |
| `ks ledger digest [--task T] [--agent A] [--json]` | the ledgers read back as decision context: blocked gates, decisions in force, pending decisions, open issues, work in flight, recent lessons/changes; `--task` narrows to one task and adds its evidence chain; `--agent` shows the briefing a subagent would receive | `digest.py` |
| `ks ledger export all \| <kind>[,<kind>…] [--out FILE] [--archive] [--session TOKEN] [--csv DIR]` | formatted Excel workbook (Summary + one sheet per kind: shards merged, header frozen, autofilter, wrapped memos, real datetimes; `--archive` adds archived entries, `--session` one session's shards, `--csv` writes CSV files instead). Default `.agents/workarea/exports/ledgers-<stamp>.xlsx` | `export_ledgers.py` + `xlsx_lite.py` (std lib) |
| `ks ledger archive-plan [--dry-run]` | move fully COMPLETED, superseded plan blocks to `archive/tasks.md`; migrates legacy `tasks-archive.md` | `archive_ledger.py plan` |
| `ks ledger archive <ledger|all> --before YYYY-MM-DD [--dry-run]` | move closed history to `archive/<ledger>.yaml` (see eligibility) | `archive_ledger.py` |
| `ks harness sync [--check]` | render harness mirrors in a full-mode project | `sync_harness.py` |
| `ks harness retrust [--ack]` | compare hook-file hashes with the last acknowledgement; exit 1 and instructions when Codex `/hooks` re-trust is needed; `--ack` records | `~/.config/tksfw/trust.json` |
| `ks help [<command>]` | the command list, or the full guide of one command (`self`, `operator`, `project`, `routing`, `hil`, `layers`, `ledger`, `harness`, `doctor`, `dev`); `ks <command> --help` is the same | — |
| `ks doctor` | runtime, home, operator, harness settings, project state, cloud-sync warning, routing, sessions, trust; exit 1 on FAIL | — |
| `ks dev build` / `test` / `release <v>` | repository checkout only | `build_plugin.py`, `tests/run_tests.py`, `release.sh` |

## Effects and safety

Every mutating verb ends with an effect line: **next spawn** (`routing use`), **next prompt** (`operator set`, `project enable`, `layers pin`), **next session** (`project update`, `harness sync` — restart, Codex `/hooks` re-trust, then `ks harness retrust --ack`), **files** (`ledger archive*`, `project disable`). `routing use` refuses while subagents are running and `project update` while sessions are active (`--force` overrides). The UserPromptSubmit hook tells the model what changed at its next prompt, so `ks` can be used while a session is open (`docs/operations.md`).

## Ledger archives

| Item | Rule |
|---|---|
| Location | `.agents/workarea/archive/<ledger>.yaml` (changes, lessons, handoffs, events, decisions) and `archive/tasks.md` — one cumulative, append-only archive per type, same schema as the live file |
| Move protocol | Append to the archive first, then remove from the live file. The PostToolUse hook accepts an ID leaving a live ledger only if it is already in `archive/<same ledger>`; archives never lose an ID |
| Eligibility | events: `Status ≠ OPEN` and older than `--before`; handoffs: BEGIN+END pairs both older; decisions: `SUPERSEDED`/`DEPRECATED` only (ACCEPTED decisions are in force); changes/lessons: by date; plan: fully COMPLETED blocks followed by a newer block |
| Readers | `cross_check` resolves foreign keys into archives (evidence links stay valid); STATE.md and `verify-integrity` lint live files only; `find` searches both |
| Legacy | `tasks-archive.md` is migrated into `archive/tasks.md` by `archive-plan`; both are accepted by the guard until then |

## Not in P0

| Command | Planned | Note |
|---|---|---|
| `ks update check` / `apply` | P1 | `git ls-remote --tags` against the marketplace repo; per-harness update commands |
| `ks routing pull` | P2 | remote routing tables — pinned repo, `--check`, diff before write; own ADR |

## Output conventions (3.7.0)

One renderer inside `tools/ks` draws every screen; nothing else is added to the dependency set (standard library only).

| Rule | Detail |
|---|---|
| Header | `ks <version> · TKSfw · <verb>` with the project name on the right and its full path below — on view commands only (`project status`, `project sessions`, `doctor`, `routing list`, `help`), never on effect commands. The name is the `title` in the spec's frontmatter, else the archetype's, else the folder name |
| Colour | Semantic, never decorative: green `✓ ●` ok/armed · yellow `!` needs attention · red `✗` refused · cyan = identifiers you can type (tokens, tables, layer names, commands in hints) · dim = context. On only when stdout is a TTY, `NO_COLOR` is unset, `TERM` is not `dumb`, and neither `--no-color` nor `--plain` was passed; `--color` forces it (`ks doctor --color \| less -R`). See the [CLI Guidelines](https://clig.dev/) and the [NO_COLOR standard](https://no-color.org/) |
| Symbols | `✓ ● ! ✗ → · ←`; `--ascii` (or a non-UTF-8 stream) swaps in `OK ON WARN FAIL -> - <-` |
| Layout | Two-column key/value blocks with the status in a right column; tables with a dim header row; sections in bold capitals separated by one blank line; 2-space indents; no box drawing. A finding's hint (`→ command`) sits on the same line when it fits the terminal width, otherwise on its own line under the finding — findings are never truncated |
| `--plain` | One record per line (`key value k=v …`), no header, colour, symbols or padding — for `grep`, hooks and the model. Also the shape used when `ks` is called from a hook |
| `--json` | `project status`, `project sessions`, `doctor` (findings with section/status/text/hint), plus the existing `drift`, `layers resolve`, `ledger digest`/`find`, `hil` |
| Errors | `✗ <verb>: <what> — <fix>` on stderr, the fix being a command in cyan; exit 1. Refusals list what blocks them (e.g. the active sessions) and both ways out (`--session`, `--force`) |
| Help | `ks help`: description, three examples, verbs, global options. `ks help <verb>`: capitalised headings, `!` notes for surprising behaviour, examples |
