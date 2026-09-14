# Getting started — from zero to the first armed project

Once per machine (steps 1–7), once per project (8–10). Commands are for macOS/Linux with zsh or bash.

## Prerequisites

| Requirement | Check |
|---|---|
| Python ≥ 3.11 (`tomllib`) | `python3 --version` |
| git ≥ 2.20 | `git --version` (worktree isolation; optional otherwise) |
| Codex CLI and/or Claude Code, current versions, with plugins enabled | `codex --version` · `claude --version` |

## Two choices before you start

### Choice 1 — where the framework comes from (source)

| Source | Who it is for | What you get | `<home>` in the steps below |
|---|---|---|---|
| **A. ZIP bundle** `dist/tksfw-<v>.zip` (recommended for users) | Anyone using the framework; no git access to the TKSfw repo needed | The framework bundle, unzipping to `tksfw/`: both marketplace catalogs (`.agents/plugins/`, `.claude-plugin/`), the built plugins `plugins/tksfw`, `plugins/tksfw-tools`, the `docs/`, README, CHANGELOG, CREDITS. `ks` is inside the plugin at `plugins/tksfw/bin/ks` | the unzipped folder, `~/tksfw` |
| **B. Git checkout** of the TKSfw repository | Framework maintainers, or teams that track releases with `git pull` | The full repo: sources, `template/`, `tools/ks`, tests, docs, and the same committed `plugins/` — the repo root is itself a marketplace | the checkout, e.g. `~/tksfw` |

The other archives in `dist/` are not needed for this guide: `tksfw-plugin-<v>.zip` / `tksfw-tools-plugin-<v>.zip` are single-plugin archives for Claude Code's `archive` source or a hand-built personal marketplace; `tksfw-template-<v>.zip` is the bare project template (`docs/distribution.md`).

Both unpack to `~/tksfw`, which is also the folder you register as marketplace. The only differences between A and B are the paths of `ks` and of the completion script (`plugins/tksfw/bin/` in the bundle, `tools/` in the checkout). The steps table shows both.

### Choice 2 — where the framework runs (install level)

| Level | Command | How it works | Choose it when |
|---|---|---|---|
| **User level — plugin mode** (recommended) | `ks project init` | Hooks and skills run from the plugin installed in each harness (Codex `/plugins`, `claude plugin install`). A project gets only the thin layer: `AGENTS.md`, `CLAUDE.local.md` (Claude Code entry, `@AGENTS.md`), `.agents/{workarea,agents,config.toml}`, `.codex/config.toml` (permission profile), `.claude/settings.json` (the same deny rules for Claude Code). No `.claude/skills` or hooks in the project: they come from the plugin; `.codex/agents/` and `.claude/agents/` appear when the first agent is defined. Updating the plugin updates every project at once; the guard in `.agents/.tksfw.json` arms/disarms per project | You work on your own machine(s); you want one install and one update path; projects should stay small and free of framework code |
| **Project level — full mode** | `ks project init --full` | Hooks and skills are copied into the project (`.agents/hooks/`, `.agents/skills/`) and pinned to that version; the plugin, if installed, yields to them. Everything a session needs travels with the repository | The repository is shared with people who will not install the plugin (customer teams, CI, air-gapped machines), or the project must be frozen at a framework version regardless of what is installed on the machine |

Rationale: the method (AGENTS.md, ledgers, plan) is always project-local — that never changes. What moves is the **tooling**: keeping it in the plugin avoids ~45 framework files in every repo and gives one place to update and re-trust; copying it in makes the repo self-sufficient at the price of per-project updates (`ks project update`) and per-project hook trust in Codex. Both modes are managed by the same `ks` commands. Switching later is a re-initialisation, not an update: plugin → full is `rm .agents/.tksfw.json && ks project init --full` (existing ledgers, plan and agents are kept — only the missing tooling files are added); full → plugin is the same with `ks project init`, then delete `.agents/hooks/`, `.agents/skills/` and the `.claude/skills/` mirror by hand. `ks` itself is always installed at user level (step 2), even if your projects are full mode.

## Steps

| # | Step | A — ZIP bundle | B — Git checkout |
|---|---|---|---|
| 1 | Get the framework | `unzip tksfw-<v>.zip -d ~` → creates `~/tksfw/` (the archive has one top-level folder; that folder is `<home>`) | `git clone <TKSfw repo> ~/tksfw` |
| 2 | Put `ks` on PATH | `python3 ~/tksfw/plugins/tksfw/bin/ks self install` | `python3 ~/tksfw/tools/ks self install` |
|   | | Both: adds `~/.local/bin/ks` (symlink) and records `<home>` in `~/.config/tksfw/user.toml`; prints the completion line and a note if `~/.local/bin` is not on your PATH | |
| 3 | Register the marketplace, install the plugin | Codex: `codex plugin marketplace add ~/tksfw` | same |
|   | | Both: in Codex `/plugins` → install **tksfw** (and **tksfw-tools** if you use the Perplexity/Playwright MCP servers) → restart → `/hooks` → trust. Claude Code: `claude plugin marketplace add <home>` then `claude plugin install tksfw@tksfw --scope user` (+ `tksfw-tools@tksfw` optional). Full-mode-only users can skip this step: a full-mode project carries its own hooks and skills, and the bootstrap stanza comes from step 4, not from the plugin | |
| 4 | One-shot user setup | `ks self setup --operator "Your Name"` — sets the operator (step 5), appends the bootstrap stanza to `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md` (idempotent), prints the completion hint | same |
| 5 | Operator name (if you skipped `--operator`) | `ks operator set "Your Name"` → `~/.config/tksfw/user.toml`; every ledger entry you write carries it | same |
| 6 | Shell completion (optional) | add `source ~/tksfw/plugins/tksfw/bin/ks-completion.sh` to `~/.zshrc` / `~/.bashrc` | add `source ~/tksfw/tools/ks-completion.sh` |
| 7 | Verify the install | `ks doctor` — must show 0 FAIL; each WARN names the step that fixes it. `ks self home` prints `<home>` as recorded | same |
| 8 | Create (arm) a project | `cd <project> && ks project init` (plugin mode, recommended) or `ks project init --full` (project level — see Choice 2). The command ends with "Recorded: install of v<v> …" (the first session logs the install in `changes.yaml`; nothing to write by hand) and a mode-specific "Next steps" list — follow it | same |
| 8b | Describe the project (optional, recommended) | Put the archetype in `KS_PROJECT.md` (ARCHETYPE layer: what kind of project this is and how such projects run) and the project spec in `KS_SPEC.md` (PROJECT layer: what this one must deliver) at the project root. Other names or folders: `ks layers pin --archetype <path> --spec <path>`. The spec alone is fine | same |
| 9 | First session | Launch Codex or Claude Code in the project. Codex asks once to trust the project `.codex` layer — accept; in **full mode** it also lists the project's own hooks: `/hooks` → trust. SessionStart shows the session token, operator, routing table, the project layers (archetype / spec) and the pending install record. Start the run with the `ks-start` skill — Codex: type `$ks-start` (or `/skills` and pick it); Claude Code: `/tksfw:ks-start` (`/ks-start` also works when no other command has that name). Codex has no project-level slash commands: custom prompts are deprecated and read only from `~/.codex/prompts/` ([Codex custom prompts](https://developers.openai.com/codex/custom-prompts)) | same |
| 10 | Verify | `ks doctor` in the project: 0 FAIL means ready. **Full mode only**: `ks harness retrust --ack` after trusting the hooks. In plugin mode the hooks belong to the installed plugin — there is nothing to re-trust per project; `ks doctor` / `ks harness retrust` tell you when a framework upgrade needs it | same |

If you ever run `ks` from a place it cannot resolve, set `TKSFW_HOME=<home>` (the bundle folder or the checkout; the plugin inside a bundle is found automatically) — the lookup order is `TKSFW_HOME`, `~/.config/tksfw/user.toml`, the script's own location, then the harness plugin caches.

## If step 3 fails

| Message | Cause | Fix |
|---|---|---|
| `failed to load configuration … legacy \`profile = "<name>"\` config is no longer supported; use --profile <name> with <name>.config.toml` | Codex ≥ 0.15x dropped the top-level `profile` key and the `[profiles.<name>]` tables in `~/.codex/config.toml` (not written by TKSfw; a pre-existing personal setting). Every `codex` command fails until it is fixed | Delete the `profile = …` line; move the keys you want as machine defaults (`model`, `model_reasoning_effort`, `sandbox_mode`) to the top level; move each `[profiles.<name>]` table into its own file `~/.codex/<name>.config.toml` (plain names only — `sol`, not `gpt-5.6-sol`) and select it with `codex --profile <name>` ([Codex config reference](https://developers.openai.com/codex/config-reference)) |
| `failed to create marketplace install directory ~/.codex/.tmp/marketplaces: Operation not permitted` | The shell running `codex` cannot write to `~/.codex` (sandboxed or remote shell) | Run the command in your own terminal |

## If the first session fails to start

| Message | Cause | Fix |
|---|---|---|
| `Error loading configuration: filesystem path \`_archive/**\` must be absolute, use \`~/...\`, or start with \`:\`` | The project's `.codex/config.toml` predates 2.5.1 (old permission syntax) | `ks project update` in the project (refreshes an unmodified `.codex/config.toml`); if you edited it, replace the `[permissions.hardened.filesystem]` table with the 2.5.1 template (`extends = ":workspace"`, deny rules under `[permissions.hardened.filesystem.":workspace_roots"]`) |
| The archive/backup folders are still readable by the agent | `sandbox_mode` is set in `~/.codex/config.toml` or the selected `--profile`; Codex then ignores `default_permissions` (permission profiles do not compose with the older sandbox settings — [Codex permissions](https://developers.openai.com/codex/permissions)) | Remove `sandbox_mode` from the user config to let the project profile apply, or accept the older sandbox behaviour |

## After that

| Need | Command |
|---|---|
| Check the model routing this machine will use | `ks routing list` shows the tables (`ibm-anthropic-cc` — the default — and `ibm-openai-cc` for Claude Code, `ibm-anthropic` and `ibm-openai` for Codex, …) and which one is active; `ks routing show` the effective one; pin with `ks routing use <table>` |
| See where a project stands | `ks project status` |
| Change or move the archetype / spec files | edit them (Layer ARCHETYPE / PROJECT in `changes.yaml`); the next start reports *changed*; `ks layers resolve` at any time; `ks layers pin` for other paths |
| Upgrade the framework | A: `rm -rf ~/tksfw && unzip tksfw-<v>.zip -d ~` (replace the folder; `ks`, `user.toml` and the marketplace registration all point at `~/tksfw`, so nothing else moves) · B: `git -C ~/tksfw pull`. Then: restart Codex (Claude: `claude plugin marketplace update tksfw && claude plugin update tksfw@tksfw`), `ks harness retrust` (re-trust in `/hooks` if asked, then `--ack`), `ks doctor`, and `ks project update` in each project (required in full mode, refreshes the thin layer in plugin mode) — `docs/operations.md` |
| Everyday operations (switch routing, archive, second session, reset) | `docs/operations.md` |
| All commands | `ks help`, `ks help <command>`; `docs/ks.md` |

## Uninstall

| Scope | Action |
|---|---|
| One project | `ks project disable` (inert, files kept) or delete `.agents/`, `AGENTS.md`, `CLAUDE.local.md`, `.codex/` |
| User level | Codex `/plugins` → remove tksfw; `claude plugin uninstall tksfw@tksfw`; remove the stanza block from `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`; `rm -r ~/.local/bin/ks ~/.config/tksfw`; delete `<home>` (`~/tksfw`) |
