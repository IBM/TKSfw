# tksfw-tools — bundled MCP servers

Second plugin in the marketplace. It carries the two MCP servers AGENTS.md § Tools prescribes;
`tksfw` (method tooling) does not depend on it, so users who already run these servers user-level
install `tksfw` alone and avoid duplicate browser processes and duplicate tools.

| Server | Source | Codex definition (`mcp/codex.json`) | Claude Code definition (`mcp/claude.json`) |
|---|---|---|---|
| `perplexity` | `npx -y @perplexity-ai/mcp-server` ([Perplexity docs](https://docs.perplexity.ai/docs/getting-started/integrations/mcp-server)) | `env_vars = ["PERPLEXITY_API_KEY"]` — the shell variable is whitelisted, never copied | `env.PERPLEXITY_API_KEY = "${user_config.perplexity_api_key}"` — prompted on enable (`userConfig`, `sensitive`), stored in the keychain |
| `playwright` | `npx -y @playwright/mcp --isolated --output-dir …` ([Playwright MCP](https://github.com/microsoft/playwright-mcp)) | `--output-dir .playwright` (relative to the server's working directory) | `--output-dir ${CLAUDE_PROJECT_DIR}/.playwright` |

Why two JSON files: the secret mechanisms differ per harness and each manifest's `mcpServers` field
may point to its own file. Timeouts (`startup_timeout_sec = 120`) cover the first `npx` download;
Codex's default is 10 s.

## Prerequisites and the check hook

`hooks/check_tools.py` runs at SessionStart (`startup|resume`) and adds one advisory line per missing
item: `npx` on PATH, a Playwright browser in the Playwright cache (`npx playwright install chromium`),
the API key (`PERPLEXITY_API_KEY`, or the plugin option exported as
`CLAUDE_PLUGIN_OPTION_PERPLEXITY_API_KEY`), and it creates `<project>/.playwright/`. Neither plugin
system runs install scripts, so browsers must be installed once by the user.

## Install

Same marketplace as `tksfw` (see `distribution.md`): Codex `/plugins` → **tksfw-tools** → restart →
`/hooks` trust; Claude Code `claude plugin install tksfw-tools@tksfw` → answer the API-key prompt.
Disable one server without editing the plugin: Codex `[plugins."tksfw-tools".mcp_servers.playwright] enabled = false`
([Codex packaging](https://developers.openai.com/plugins/build/plugins)); Claude Code configures plugin servers independently of user servers.

## Tool names

| Harness | Names the skills see |
|---|---|
| Codex | `perplexity_search`, `perplexity_ask`, `perplexity_research`, `perplexity_reason`; Playwright `browser_*` |
| Claude Code | scoped: `mcp__plugin_tksfw-tools_perplexity__perplexity_search`, `mcp__plugin_tksfw-tools_playwright__browser_navigate` … — hook matchers must use the scoped form |

## To verify once per machine

| Check | How |
|---|---|
| Codex working directory of stdio servers | take one screenshot; it must land in `<project>/.playwright/`. If not, add `"cwd"` to the playwright entry in `mcp/codex.json` |
| First start within timeout | `codex` → `/mcp` shows both servers connected; Claude Code `/mcp` likewise |
| Key reaches the server | `perplexity_search` returns results; a 401 means the variable/option is missing |
