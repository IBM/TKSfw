# Getting started — from zero to the first armed project

Ten steps, once per machine (steps 1–7) and once per project (8–10). Commands are for macOS/Linux with zsh or bash.

## Prerequisites

| Requirement | Check |
|---|---|
| Python ≥ 3.11 (`tomllib`) | `python3 --version` |
| git ≥ 2.20 | `git --version` (worktree isolation; optional otherwise) |
| Codex CLI and/or Claude Code, current versions, with plugins enabled | `codex --version` · `claude --version` |

## Steps

| # | Step | Command / action |
|---|---|---|
| 1 | Get the framework | `git clone <TKSfw repo> ~/tksfw` — or unzip `dist/tksfw-marketplace-<v>.zip` to a folder `<home>` |
| 2 | Put `ks` on PATH | `python3 ~/tksfw/tools/ks self install` (adds `~/.local/bin/ks`, records the home in `~/.config/tksfw/user.toml`) — from an unzipped bundle: `python3 <home>/plugins/tksfw/bin/ks self install` |
| 3 | Register the marketplace and install the plugin | Codex: `codex plugin marketplace add ~/tksfw` → in Codex `/plugins` → install **tksfw** (and **tksfw-tools** if you use the Perplexity/Playwright MCP servers) → restart → `/hooks` → trust. Claude Code: `claude plugin marketplace add ~/tksfw` then `claude plugin install tksfw@tksfw --scope user` (+ `tksfw-tools@tksfw` optional) |
| 4 | One-shot user setup | `ks self setup --operator "Your Name"` — sets the operator (step 5), appends the bootstrap stanza to `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md` (idempotent), prints the completion hint |
| 5 | Operator name (if you skipped `--operator`) | `ks operator set "Your Name"` → `~/.config/tksfw/user.toml`; every ledger entry you write carries it |
| 6 | Shell completion (optional) | add `source ~/tksfw/tools/ks-completion.sh` to `~/.zshrc` / `~/.bashrc` |
| 7 | Verify the install | `ks doctor` — must show 0 FAIL; WARN lines name the step that fixes them |
| 8 | Create (arm) a project | `cd <project> && ks project init` (tooling from the plugin) or `ks project init --full` (self-contained: hooks and skills copied in-tree, no plugin dependency) |
| 9 | First session | Launch Codex or Claude Code in the project. SessionStart shows the session token, operator and routing table. Codex asks to trust the project `.codex` layer (and the hooks in full mode) |
| 10 | Acknowledge the hooks | After trusting in Codex: `ks harness retrust --ack`. From now on `ks doctor` / `ks harness retrust` tell you when a framework update needs re-trusting |

## After that

| Need | Command |
|---|---|
| Check the model routing this machine will use | `ks routing show` — the provider table (`[routing.<provider>]` in `.agents/models.toml`) must match your endpoint; pin one with `ks routing use <table>` |
| See where a project stands | `ks project status` |
| Everyday operations (switch routing, update, archive, second session, upgrade) | `docs/operations.md` |
| All commands | `docs/ks.md` |

## Uninstall

| Scope | Action |
|---|---|
| One project | `ks project disable` (inert, files kept) or delete `.agents/`, `AGENTS.md`, `CLAUDE.local.md`, `.codex/` |
| User level | Codex `/plugins` → remove tksfw; `claude plugin uninstall tksfw@tksfw`; remove the stanza block from `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`; `rm ~/.local/bin/ks ~/.config/tksfw -r` |
