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
| `ks project status` | version vs installed, mode, armed, drift counts, active sessions, plan focus, isolation spaces | manifest, `--drift --json`, STATE.md, `workarea.py status` |
| `ks project drift [--json]` | unchanged / outdated / edited / missing per file; exit 1 on drift; writes nothing | `new_project.py --drift` |
| `ks project reset [--archive [--label L]] [--keep-agents] [--registry] [--dry-run] [--yes] [--force]` | start over: clears ledgers (all shards + legacy), archives, `tasks.md`, STATE.md, exports, hook state (all hosts), work areas, worktrees, agent definitions + mirrors. `--archive` moves ledgers/plan/archives/exports/work areas/agents to `.agents/history/<stamp>[-label]/` instead (hook state is always deleted; worktree branches kept). Registry kept unless `--registry`; agents kept with `--keep-agents`. Refuses while sessions are active, without `--yes` (non-interactive) or with unmerged worktree branches (`--force`). Records the generation in `.agents/.tksfw.json` → SessionStart and STATE.md announce "Generation N" | — |
| `ks routing show` / `check` / `resolve <agent>` | resolved table, validation, one agent's model | `route_model.py --print/--check/--resolve` |
| `ks routing use <table>` / `use --clear` | pin a routing table (`selected = "<table>"` in `models.toml`, read after `TKSFW_ROUTING`, before the provider match) | edits `models.toml`, then `--check` |
| `ks ledger check` | validate every live ledger and archive, lint `tasks.md`, cross-check FKs | `validate_yaml_log.py`, `tasks_lint.py`, `cross_check.py` |
| `ks ledger find <id> [--refs] [--json]` / `find --prefix <chars>` | locate an entry or task across live files, archives and plan; `--refs` lists everything that references it | `find_entry.py` |
| `ks ledger digest [--task T] [--agent A] [--json]` | the ledgers read back as decision context: blocked gates, decisions in force, pending decisions, open issues, work in flight, recent lessons/changes; `--task` narrows to one task and adds its evidence chain; `--agent` shows the briefing a subagent would receive | `digest.py` |
| `ks ledger export all \| <kind>[,<kind>…] [--out FILE] [--archive] [--session TOKEN] [--csv DIR]` | formatted Excel workbook (Summary + one sheet per kind: shards merged, header frozen, autofilter, wrapped memos, real datetimes; `--archive` adds archived entries, `--session` one session's shards, `--csv` writes CSV files instead). Default `.agents/workarea/exports/ledgers-<stamp>.xlsx` | `export_ledgers.py` + `xlsx_lite.py` (std lib) |
| `ks ledger archive-plan [--dry-run]` | move fully COMPLETED, superseded plan blocks to `archive/tasks.md`; migrates legacy `tasks-archive.md` | `archive_ledger.py plan` |
| `ks ledger archive <ledger|all> --before YYYY-MM-DD [--dry-run]` | move closed history to `archive/<ledger>.yaml` (see eligibility) | `archive_ledger.py` |
| `ks harness sync [--check]` | render harness mirrors in a full-mode project | `sync_harness.py` |
| `ks harness retrust [--ack]` | compare hook-file hashes with the last acknowledgement; exit 1 and instructions when Codex `/hooks` re-trust is needed; `--ack` records | `~/.config/tksfw/trust.json` |
| `ks doctor` | runtime, home, operator, harness settings, project state, cloud-sync warning, routing, sessions, trust; exit 1 on FAIL | — |
| `ks dev build` / `test` / `release <v>` | repository checkout only | `build_plugin.py`, `tests/run_tests.py`, `release.sh` |

## Effects and safety

Every mutating verb ends with an effect line: **next spawn** (`routing use`), **next prompt** (`operator set`, `project enable`), **next session** (`project update`, `harness sync` — restart, Codex `/hooks` re-trust, then `ks harness retrust --ack`), **files** (`ledger archive*`, `project disable`). `routing use` refuses while subagents are running and `project update` while sessions are active (`--force` overrides). The UserPromptSubmit hook tells the model what changed at its next prompt, so `ks` can be used while a session is open (`docs/operations.md`).

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
