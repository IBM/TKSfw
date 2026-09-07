# tksfw-tools plugin

Companion of `tksfw`: the two MCP servers the TKS method prescribes (AGENTS.md § Tools).

| Server | Command | Secret | Notes |
|---|---|---|---|
| `perplexity` | `npx -y @perplexity-ai/mcp-server` | `PERPLEXITY_API_KEY` — Codex: whitelisted from your shell (`env_vars`); Claude Code: prompted on enable (`userConfig`, keychain) | tools `perplexity_search`, `perplexity_ask`, `perplexity_research`, `perplexity_reason` |
| `playwright` | `npx -y @playwright/mcp --isolated --output-dir <project>/.playwright` | none | isolated profile; artifacts stay in `.playwright/` (method rule) |

Do not install this plugin if you already run these servers user-level: you would get two browser
processes and duplicate tools. Both harnesses let you disable one server without editing the plugin
(Codex `[plugins."tksfw-tools".mcp_servers.<server>] enabled = false`; Claude Code `/plugin` → configure).

Prerequisites: Node.js with `npx`; Playwright browsers (`npx playwright install chromium`); the API
key. The `check_tools.py` SessionStart hook reports what is missing.

Claude Code tool names are scoped: `mcp__plugin_tksfw-tools_perplexity__perplexity_search`.

GENERATED copy — edit `plugin-src/tksfw-tools/` in the TKSfw repository and rebuild.
