<!-- TKSfw bootstrap stanza — append to ~/.claude/CLAUDE.md (Claude Code). Concatenated before every
     project's CLAUDE.md, so keep it short. Per-project hard off: "enabledPlugins": {"tksfw@tksfw": false}
     in .claude/settings.local.json; normal off: "enabled": false in .agents/.tksfw.json (tksfw-init --disable). -->

# TKS framework (tksfw plugin) — bootstrap

- The TKS method governs a project ONLY when the project contains `.agents/.tksfw.json` with `enabled`
  not false; there, `CLAUDE.local.md` imports the project's `AGENTS.md`, which carries the rules, and the
  plugin's hooks and skills (`tksfw:*`) are active. Follow that `AGENTS.md`.
- In any other folder the framework is inert: do not create `.agents/`, ledgers or `AGENTS.md`, and do
  not apply the method's ledger/agent rules.
- If the user asks to apply, initialise or set up the TKS method/framework in a project, or to update,
  disable or enable it, use the `tksfw:tksfw-init` skill. Never initialise a project unasked.
