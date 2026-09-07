<!-- TKSfw bootstrap stanza — append to ~/.codex/AGENTS.md (Codex). Keep it short: this file shares the
     32 KiB project_doc_max_bytes budget with every project's own AGENTS.md. -->

# TKS framework (tksfw plugin) — bootstrap

- The TKS method governs a project ONLY when the project contains `.agents/.tksfw.json` with `enabled`
  not false; in such a project, the project's own `AGENTS.md` carries the rules and the plugin's hooks
  and skills are active. Follow that `AGENTS.md`.
- In any other folder the framework is inert: do not create `.agents/`, ledgers or `AGENTS.md`, and do
  not apply the method's ledger/agent rules.
- If the user asks to apply, initialise or set up the TKS method/framework in a project, or to update,
  disable or enable it, use the `tksfw-init` skill. Never initialise a project unasked.
