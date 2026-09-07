# GENERATED — do not edit here

Everything under `plugins/` is produced by `python3 tools/build_plugin.py` (or `ks dev build`) from:

| Source | Becomes |
|---|---|
| `template/.agents/hooks/`, `template/.agents/skills/` | `plugins/tksfw/hooks/`, `plugins/tksfw/skills/` (hook commands rewritten to `${CLAUDE_PLUGIN_ROOT}`, skill tests dropped) |
| `plugin-src/tksfw/` | manifests, README, `skills/tksfw-init/`, `bootstrap/` (version injected) |
| `template/` + `tools/new_project.py` + `VERSION` | `plugins/tksfw/skills/tksfw-init/assets/` |
| `tools/ks`, `tools/ks-completion.sh` | `plugins/tksfw/bin/` |
| `plugin-src/tksfw-tools/` | `plugins/tksfw-tools/` (verbatim, version injected) |

It is committed because both marketplace catalogs (`.agents/plugins/marketplace.json`, `.claude-plugin/marketplace.json`)
point at `./plugins/<name>`, so `codex plugin marketplace add <checkout>` / `claude plugin marketplace add <checkout>`
work from a plain clone. `tests/run_tests.py` fails when this copy is stale; `tools/build_plugin.py --check` reports it.
