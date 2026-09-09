# User-level deployment — install once, arm per project

The project folder stays the unit of work (AGENTS.md, workarea, ledgers, `config.toml`, agent sources
live there). What the user-level shape adds: the tooling is installed once per user, is **inert** in
every folder that has not opted in, and can create or disarm a project instance on request.

## Install once (per machine, per harness)

| Step | Codex | Claude Code |
|---|---|---|
| Marketplace | `codex plugin marketplace add <TKSfw checkout or unzipped bundle, e.g. ~/tksfw>` | `claude plugin marketplace add <same>` |
| Plugin | `/plugins` → **tksfw** (and optionally **tksfw-tools**) → restart → `/hooks` trust | `claude plugin install tksfw@tksfw --scope user` (`tksfw-tools@tksfw` optional) |
| Bootstrap stanza | append `plugins/tksfw/bootstrap/AGENTS.global.md` to `~/.codex/AGENTS.md` | append `plugins/tksfw/bootstrap/CLAUDE.global.md` to `~/.claude/CLAUDE.md` |

The stanza is short on purpose: `~/.codex/AGENTS.md` shares the 32 KiB `project_doc_max_bytes` budget
with every project's own AGENTS.md ([Codex AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md)),
and `~/.claude/CLAUDE.md` is concatenated before every project file ([Claude Code memory](https://code.claude.com/docs/en/memory)).
It says three things: the method applies only where `.agents/.tksfw.json` is enabled; elsewhere do
nothing; use `tksfw-init` when asked to set up a project.

## The `ks` command

`python3 <plugin root>/bin/ks self install` puts `ks` on PATH and records the framework home; from then on every operation below is a `ks` verb (`ks operator set`, `ks project init|update|status|drift|enable|disable`, `ks routing use`, `ks ledger …`, `ks harness retrust`, `ks doctor`). Reference: `docs/ks.md`.

## Operator name (required for ledger entries)

Every ledger entry records `OwnerSessionUserName`. The configuration item is per user, not per project
(a shared repository cannot hold personal identity):

| Item | Value |
|---|---|
| File | `~/.config/tksfw/user.toml` (override the directory with `TKSFW_CONFIG_DIR`) |
| Schema | `schema = 1` · `name = "Carlos Veira"` |
| Set it | `python3 tools/new_project.py --set-operator "Carlos Veira"` (repo) or the `tksfw-init` skill (`… assets/new_project.py --set-operator "…"`) |
| Check it | `python3 tools/new_project.py --show-operator` → name and source; exit 1 when unset |
| Override | `TKSFW_USER` environment variable (CI, one-off shells) — wins over the file |
| Fallback | `git config user.name` — used when neither is set, and reported as "(from git config — set it)" at session start so the gap is visible |

The SessionStart hook shows the resolved value on every start; ledger entries without the field are rejected by the PostToolUse hook.

## What happens in a folder

| Folder state | Hooks | Skills | Model routing |
|---|---|---|---|
| No `.agents/.tksfw.json` (and no `AGENTS.md`/`.agents/workarea`) | exit 0 before touching anything — nothing is created | visible but the stanza says not to apply the method | none |
| `.tksfw.json` with `"enabled": true` (plugin-mode project) | active; state in `.agents/workarea/.hook-state/` | active | active |
| `.tksfw.json` with `"enabled": false` | inert | visible, inert by instruction | none |
| Project with its own `.agents/hooks/hooks.json` (full mode) | plugin instance **yields**; the in-project hooks run | both sets visible (Claude Code namespaces the plugin's) — prefer one layout per project | in-project hook |

## Arm, update, disarm — from the plugin

The `tksfw-init` skill (`$tksfw-init` in Codex, `/tksfw:tksfw-init` in Claude Code) wraps the same
installer the repository uses, with the template bundled in the plugin:

| Goal | Command run by the skill |
|---|---|
| New plugin-mode project | `python3 <plugin>/skills/tksfw-init/assets/new_project.py <project> --plugin-mode` |
| New self-contained project | `… <project>` |
| Update to the installed version (locally edited files kept and listed) | `… <project> --update` |
| Disarm / re-arm | `… <project> --disable` / `--enable` |

`inject_state.py` warns at session start when the project manifest and the installed plugin differ
in major.minor; `--update` clears it.

## Per-project off switches

| Switch | Harness | Effect |
|---|---|---|
| `"enabled": false` in `.agents/.tksfw.json` (`tksfw-init --disable`) | both | hooks and routing inert; files untouched; the stanza tells the model the method does not apply |
| `"enabledPlugins": {"tksfw@tksfw": false}` in `.claude/settings.local.json` (you) or `.claude/settings.json` (team) | Claude Code | plugin fully unloaded for that project; project settings beat user settings ([settings reference](https://code.claude.com/docs/en/settings-reference)) |
| `disableAllHooks: true` in a project settings file | Claude Code | all non-managed hooks off |
| `/plugins` → Space on **tksfw** | Codex | user-wide, not per project — use the manifest switch for one project |

The manifest is the source of truth: it is the only switch that behaves identically on both harnesses
and survives a plugin update.

## Two sessions on one project

Tolerated and guarded, not a design target. Each session gets a token at start; the hooks attribute changes per session, keep the live-subagent cap per session, key work areas by `<session>.<task>.<instance>`, and block lost updates on ledgers and `tasks.md` (entries that disappear are named and must be restored). A second active session is announced at SessionStart. Coordinate before editing the same files; a rewrite cannot be rolled back, only rejected.

## Constraints to remember

| Constraint | Note |
|---|---|
| Codex user-level hooks cannot be disabled by a project | "higher-precedence config layers don't replace lower-precedence hooks" ([Codex hooks](https://learn.chatgpt.com/docs/hooks)); the guard is what makes them safe |
| A Claude Code project that enables `tksfw@tksfw` in `.claude/settings.json` overrides your user-level `false` | opt out in `.claude/settings.local.json` |
| Plugin directories are ephemeral on update | nothing is written there; state is project-local |
| Provider tables | after `tksfw-init`, review `[routing.<provider>]` in `.agents/config.toml` for this machine's provider (`route_model.py --print`) |
| Re-trust | Codex asks to re-trust plugin hooks after each plugin update that changes a hook script |
