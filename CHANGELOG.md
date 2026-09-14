# Changelog

All notable changes to TKSfw. Format: Keep a Changelog; versions follow semver (`VERSION`).

## [3.7.1] — 2026-09-14

### Fixed
- Every `ks` command now renders through the 3.7.0 conventions — 3.7.0 had left the commands that delegate to framework scripts printing the scripts' own text. `new_project.py` gained `--json` for init/update/enable/disable; `ks project init|update` render a header, an INIT/UPDATE block (installed / refreshed / kept / removed / retired / unchanged, with the merge hint on kept files), MAIN SESSION MODEL, and NEXT STEPS (init) or the restart effect (update). `ks project drift` (DRIFT none/yes with per-class rows), `enable|disable` (✓ ARMED / ! DISARMED), `reset` (RESET PLAN block), `routing show` (ROUTING line + tier/model/effort/roles table, SESSION line with `--session`), `routing check|resolve` (one ✓ line: agent → role → tier → model), `hil show|set`, `layers resolve` (CORE/ARCHETYPE/SPEC block with source and title), `layers pin|journal`, `ledger check` (one finding per file, RESULT PASS/FAIL), `ledger find|digest|export|archive*`, `harness sync` (target/result/path table) and `retrust`, `self version|install|setup`, `operator set|show` restyled. Child-script output that is passed through gets its first line marked by exit code and `code` spans in cyan; `--plain` and `--json` stay raw. 2 new tests (332 total).

## [3.7.0] — 2026-09-14

### Changed
- `ks` output redesigned on one renderer (ADR 0017): header `ks <version> · TKSfw · <verb>` with the project name and path on view commands; bold section titles; key/value blocks with a right-aligned status column; tables with a dim header; semantic colour (green ok/armed, yellow attention, red refused, cyan identifiers and commands, dim context); marks `✓ ● ! ✗ →` with ASCII fallback. Colour only on a TTY with `NO_COLOR` unset and `TERM != dumb`; `--no-color`, `--color`, `--ascii`. Hints that do not fit the terminal width wrap under their finding; nothing is truncated.
- `--plain` on every command: one record per line, no header/colour/symbols/padding — for scripts, hooks and the model. `--json` for `project status`, `project sessions`, `doctor`.
- `ks project status`, `ks doctor` (RESULT line `N fail · M warn`), `ks routing list` (stacked tables, ACTIVE line, selection order), `ks routing use` (what changed, per harness; notes as hints), refusals (`✗ … — fix`, blockers listed with both ways out), `ks help` (usage, examples, verbs, options) and `ks help routing` (numbered selection order, `!` notes, examples) restyled. Project name = spec/archetype frontmatter `title`, else folder name.
- `ks layers resolve` aligns its label column. 8 new tests (330 total).

## [3.6.0] — 2026-09-14

### Changed
- Layer model by name (ADR 0016): **CORE** (`AGENTS.md` — principles, orchestration policy, agent behaviour, execution guidelines, acceptance criteria) · **ARCHETYPE** (`KS_PROJECT.md`) · **PROJECT** spec (`KS_SPEC.md`). The L1–L4 numbers are gone from the kernel, skills, hooks, `ks` and the guides; the spec overrides the archetype, neither overrides the core.
- `changes.yaml` `Layer` enum is `CORE | ARCHETYPE | PROJECT`. `METHOD` (pre-3.6.0) stays valid on read — the validator accepts it and every reader canonicalises it to `CORE` (install-log reconciliation included); new entries write `CORE`. Existing ledgers are never rewritten.
- `ks layers resolve|pin --archetype P | --spec P` (manifest keys `archetype` / `spec`). The pre-3.6.0 flags `--l3/--l4` and manifest keys `l3/l4` are still read; `pin` replaces a legacy key with the new one. Hook-state classes are `layer:archetype` / `layer:spec`; `layers.py --json` rows carry `label` and `ledger_layer`.
- SessionStart layers block: "| Archetype | … |", "| Spec | … |", "Spec overrides Archetype; neither overrides AGENTS.md (Core)". `ks project status` layers line starts with `CORE AGENTS.md`. `ks help layers` explains the model. 7 new tests (322 total).

## [3.5.0] — 2026-09-11

### Added
- `SessionEnd` hook (`session_end.py`, both harnesses): the session record is marked `ended` (with the harness's reason) the moment the main thread closes, and its live-subagent set is cleared. A closed session no longer counts as active for `ks project update|reset`, `ks routing use`, the spawn-time "other sessions" notice, STATE.md or `ks doctor` — previously it lingered up to 30 minutes after the last heartbeat. `/resume` of an ended session reopens its record. Codex: one more hook entry to trust (`ks harness retrust --ack`).
- `ks project sessions [list]` and `ks project sessions close <token>… | --stale | --all` — end records by hand when a harness quit without `SessionEnd` (older plugin, crash).
- `ks project status` explains the count ("N active (ended by the harness, or heartbeat within the last 30 min) · K ended in the last 3 h") and hints at `sessions close` when an active row is older than 10 minutes.

### Fixed
- Session records created by a Claude Code `SessionStart` showed `harness: unknown` (that payload has no `prompt_id` yet): the harness is now taken from `CLAUDE_PROJECT_DIR`/`CLAUDE_PLUGIN_ROOT`, and any remaining `unknown` is backfilled by the next heartbeat that can tell.
- `ks doctor`: the "version project X / installed Y — run `ks project update`" line is now WARN on any mismatch (it was `ok` for same-minor mismatches, which hid a refused update). 13 new tests (315 total).

## [3.4.1] — 2026-09-11

### Fixed
- Claude Code failed spawns with "Agent type 'builder' not found": the model passed a **role** as the agent type. The routing hook only checked that the name mapped to a role, so it allowed the spawn and the harness then refused it. The hook now denies a spawn whose agent has no definition (`.agents/agents/<name>.toml` missing, built-in types excepted) with the fix in the reason — "`builder` is a ROLE, not an agent — agents are named <family>-<role> (e.g. `report-builder`). Define it first with the define-agent skill …". When the source exists but the harness mirror is missing (copied project, pruned folder) it is rendered on the fly. `ks routing resolve <name>` stays informational (no existence check).
- AGENTS.md § Subagents: "the spawn's agent type is the agent's full name (`<family>-<role>`), never a bare role or tier — the hook denies spawns of undefined agents" (18,977 B; two sentences shortened). 4 new tests (302 total); the kernel-size test now reads the template, not the project copy.

## [3.4.0] — 2026-09-10

### Added
- Session-scoped routing: `ks routing use <table> --session [token]` stores the override in the session record; selection order is now session override → `TKSFW_ROUTING` → `selected` → provider match → URL match → `default_routing`. Only that session's spawns and prompt notice change ("… via session override — THIS SESSION ONLY"); `--clear --session` removes it; the override dies with the session. `ks routing show --session [token]`.
- Session identity from a shell: the SessionStart hook exports `TKSFW_SESSION=<token>` through Claude Code's `CLAUDE_ENV_FILE`, so `--session` without a token resolves exactly in Claude Code Bash commands; otherwise the only active session on this host by this operator; otherwise the candidates are listed. Session records carry `host`.
- `ks project status` prints a sessions table (token, harness, operator, host, started, last seen, routing) and marks "← this session (TKSFW_SESSION)" or "← probably yours (only session on this host by you)". STATE.md Sessions section shows overrides and hosts.

### Changed
- `ks routing use <table>` (project-wide) refuses while other sessions are active, listing them and pointing to `--session` / `--force`. ADR 0015; routing guide, operations guide, `ks help routing|project`. 16 new tests (298 total).

## [3.3.0] — 2026-09-09

### Fixed
- Claude Code rejected routed spawns with third-party ids ("Agent tool only accepts sonnet, opus, haiku, fable"): the per-spawn `model` parameter takes aliases only. The hook now injects the tier's alias for Claude Code (research → `haiku`, build → `sonnet`, judge → `opus`; override with `[claude_aliases]` in `config.toml`) and names the concrete id in `additionalContext`; `ks routing use` / `project init|update` write the alias → id map as `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL` into `.claude/settings.local.json` `env` (next launch) and re-render the agent mirrors (`.claude/agents/*.md` keep the full routed id and take precedence). Codex spawns unchanged.

### Changed
- `ks routing use` re-renders agent mirrors in plugin mode too (via `agentlib`, which the plugin ships). `sync_harness.py` honours `TKSFW_PROJECT_ROOT`. `route_model.py --main --claude` reports `alias` and `aliases`. Docs: "Claude Code and third-party model ids" (also clarifies that `.agents/agents/*.toml` is the neutral source, not a Codex file). Tests updated (282 total).

## [3.2.0] — 2026-09-09

### Added
- Main-session model follows the routing table: the orchestrator runs on the **judge tier** of the table each harness would select. `ks project init|update` and `ks routing use` write it to `.claude/settings.local.json` (`model`, project-local — wins over the user default, not template-managed) and `.codex/config.toml` (`model`, `model_reasoning_effort`), and print the `/model …` command to switch the running session now (harnesses do not re-read settings mid-session). `route_model.py --main [--codex|--claude]` prints the resolved main-session model. The prompt notice after a routing switch tells the model to ask the operator for `/model <judge model>`.
- `new_project.py` classifies and refreshes `.codex/config.toml` ignoring the `ks`-written model lines, so they never count as a local edit and survive `ks project update`. 6 new tests (280 total).

### Notes
- A pinned table applies to both harnesses; pin a `-cc` table only in projects run with Claude Code. Unpinned selection stays harness-aware.

## [3.1.1] — 2026-09-09

### Added
- `[routing.ibm-openai-cc]`: Claude Code against the IBM endpoint with OpenAI models in their 1M-context variants — gpt-5.6-luna[1m] / gpt-5.6-terra[1m] / gpt-5.6-sol[1m]. No match rule (the default remains `ibm-anthropic-cc`): `ks routing use ibm-openai-cc`. Docs, `ks help routing`, 1 new test (275 total).

## [3.1.0] — 2026-09-09

### Changed
- Preferred harness is Claude Code: new top-level `default_routing = "ibm-anthropic-cc"` in `config.toml` (selection step 5, before the legacy `[routing.default]` table); validated by `ks routing check`; `ks routing list` marks it `[default]`.
- The IBM endpoint is one Codex provider for both model families: `[routing.ibm-anthropic]` now carries `match = { codex_model_provider = "ibm" }` like `ibm-openai`, and is listed first so a Codex session on `model_provider = "ibm"` gets Anthropic models; `ks routing use ibm-openai` (or `TKSFW_ROUTING=ibm-openai`) switches. Rule made explicit: when several tables match, the first in file order wins.
- OpenRouter example table: research `google/gemini-flash-latest`, build `anthropic/claude-sonnet-latest`, judge `anthropic/claude-opus-latest`.
- `docs/model-routing.md` selection order and shipped-tables table, `ks help routing`, getting-started row; tests updated (274 total).

## [3.0.0] — 2026-09-09

Configuration file renamed and routing tables made explicit. Major version because both were part of the 2.x compatibility promise; migration is automatic.

### Changed
- `.agents/models.toml` → **`.agents/config.toml`** (it holds `[routing.*] [tiers] [roles] [naming]`, `[hil]`, `[state]`, `[delegation]`). Every reader (hooks, skill assets, `ks`) accepts the legacy name; `ks project update` renames an existing file in place — content, routing pin, HIL threshold and limits survive, and its recorded hash is carried over.
- `[routing.ibm]` → **`[routing.ibm-openai]`** with `match = { codex_model_provider = "ibm" }`. Codex selection now tries `match.codex_model_provider` first, then a table keyed by the provider id (legacy). `TKSFW_ROUTING=ibm` in shell profiles must become `ibm-openai`.

### Added
- `[routing.ibm-anthropic]` (claude-haiku-4-5 / claude-sonnet-5 / claude-opus-5) and `[routing.ibm-anthropic-cc]` (claude-haiku-4-5 / claude-sonnet-5[1m] / claude-opus-5[1m], for Claude Code). Neither carries a `match` yet: pin with `ks routing use <table>`, or add `match.codex_model_provider` / `match.claude_base_url` for the endpoint you use.
- `ks routing list`: every table with match rule, model per tier, and `[pinned]` / `[active (how)]` markers — the menu for `ks routing use`.
- `ks help [<command>]` and `ks <command> --help`: a full guide per command (self, operator, project, routing, hil, layers, ledger, harness, doctor, dev), shipped inside `ks`.
- ADR 0014; `docs/model-routing.md` "Tables shipped in the template"; `docs/ks.md`, getting-started rows. 8 new tests (272 total).

## [2.7.0] — 2026-09-09

### Fixed
- `/ks-start` was "Unrecognized command" in Codex: the template shipped Codex custom prompts under the project's `.codex/prompts/`, but Codex reads custom prompts only from `~/.codex/prompts/` (as `/prompts:<name>`) and has deprecated them in favour of skills ([Codex custom prompts](https://developers.openai.com/codex/custom-prompts)). The start is the `ks-start` skill, which both harnesses already had: Codex `$ks-start` (or `/skills`), Claude Code `/tksfw:ks-start` (`/ks-start` when unambiguous). Post-init message, AGENTS.md § Project Layers, getting-started, operations, README, ADR 0013 and the tksfw-init skill now say so.

### Changed
- `template/.codex/prompts/` removed. The reload prompt became the `ks-reload` skill (re-read AGENTS.md, L3, L4 from disk after edits; journals the hashes). Both harnesses see it (Codex `$ks-reload`, Claude Code `/tksfw:ks-reload`).
- `ks project update` now removes files the template no longer ships when they are still byte-identical to what was installed ("removed (retired by the template, pristine)"); edited copies are kept and listed for manual deletion. Existing projects lose their dead `.codex/prompts/*.md` on the next update.
- AGENTS.md 18,973 B. 2 new tests (264 total).

## [2.6.1] — 2026-09-09

### Fixed
- 2.6.0 shipped `.claude/settings.json` only in the built plugin: the source `template/.claude/settings.json` was swallowed by the `.gitignore` rule for the generated `template/.claude/` mirrors, so `tools/build_plugin.py` on a fresh checkout removed it again and the 2.6.0 tests failed (`FileNotFoundError … clprobe/.claude/settings.json`). The rule is now `template/.claude/*` with `!template/.claude/settings.json`; the source file is committed.

## [2.6.0] — 2026-09-09

### Added
- `template/.claude/settings.json`: Claude Code project settings with `permissions.deny` for `Read(./_archive/**)` and `Read(./_backup/**)` — the twin of the Codex permission profile in `.codex/config.toml`. Installed in both modes (plugin mode: 9 files); in full mode `sync_harness.py` adds the `hooks` key and keeps the rest. `ks project update` adds it to existing projects. 2 new tests (262 total).

### Clarified
- What a plugin-mode project contains for Claude Code and why there is no `.claude/skills` or hooks in it (they come from the plugin; `CLAUDE.local.md` is the entry point; `.claude/agents/` is rendered when the first agent is defined) — `docs/getting-started.md`, Choice 2.

## [2.5.1] — 2026-09-09

### Fixed
- Codex refused to start in a freshly armed project: `Error loading configuration: filesystem path \`_archive/**\` must be absolute, use \`~/...\`, or start with \`:\``. The template `.codex/config.toml` used pre-beta permission syntax (bare relative keys, value `none`). Now: `[permissions.hardened]` with `extends = ":workspace"` and the deny rules under `[permissions.hardened.filesystem.":workspace_roots"]` (`"_archive/**" = "deny"`, `"_backup/**" = "deny"`), per the [Codex permissions](https://developers.openai.com/codex/permissions) reference. Existing projects: `ks project update` refreshes an unmodified `.codex/config.toml`.
- Documented the interplay with the older sandbox settings: when `sandbox_mode` is set in `~/.codex/config.toml` or the selected profile, Codex ignores `default_permissions` (no error; the project profile simply does not apply). `docs/getting-started.md`: "If the first session fails to start" table. 1 new test (260 total).

## [2.5.0] — 2026-09-09

### Added
- Install log: `ks project init` / `update` append `{ts, version, action, mode, operator}` to `installs` in `.agents/.tksfw.json`. SessionStart tells the model "TKSfw installed/updated vX on … — not yet recorded: log it in changes.yaml (Layer METHOD)" until a METHOD-layer changes entry newer than the install exists (`hooklib.install_line`). The operator no longer has anything to write by hand.

### Changed
- Post-init/update message rewritten: "Recorded: install|update of vX in .agents/.tksfw.json — the first session logs it in changes.yaml; nothing to write by hand", then mode-specific **Next steps** — plugin mode: launch the harness, accept the `.codex` trust prompt, `ks doctor` (nothing to re-trust per project); full mode: accept `.codex` trust, `/hooks` → trust the project's own hooks, `ks harness retrust --ack`, `ks doctor`; both: optional L3/L4 files, `/ks-start`.
- `docs/getting-started.md` steps 8–10 and `docs/operations.md` "Update a project" aligned (re-trust is a full-mode / framework-upgrade matter). 6 new tests (259 total).

## [2.4.2] — 2026-09-08

### Changed (documentation)
- `docs/getting-started.md`: "If step 3 fails" table (Codex ≥ 0.15x legacy `profile =` migration to `<name>.config.toml`; "Operation not permitted" on `~/.codex/.tmp` from a sandboxed shell); "Upgrade the framework" row rewritten as the full user-level procedure.
- `docs/operations.md`: "Upgrade the framework (user level)" — replace the bundle folder (not overlay), `ks self version`, restart Codex / update the Claude plugin, `ks harness retrust` (+ `--ack`), `ks doctor`, `ks project update` per project (required in full mode, thin-layer refresh in plugin mode).

## [2.4.1] — 2026-09-08

### Fixed
- `ks doctor` warned "Codex personal marketplace: absent" although the marketplace was registered: Codex ≥ 0.15x records `codex plugin marketplace add` in `~/.codex/config.toml` (`[marketplaces.<name>] source = <dir>`), not in `~/.agents/plugins/marketplace.json`. Doctor now parses `config.toml` and reports the marketplace that points at the framework home (the hand-written personal catalog remains an accepted alternative), the plugin state (`[plugins."tksfw@tksfw"] enabled`) and hook trust (`[hooks.state."tksfw@tksfw:hooks/hooks.json:…"]` entries vs the entries in `hooks.json`), replacing the weak "config mentions hooks" line. A `config.toml` that does not parse is a FAIL with the parser message (every `codex` command fails in that state). 3 new tests (253 total).

## [2.4.0] — 2026-09-08

### Changed
- Delivery convention: the framework bundle is now `dist/tksfw-<v>.zip` and unzips to `tksfw/` (was `tksfw-marketplace-<v>.zip` → `tksfw-marketplace/`). "Marketplace" is what the harnesses call the catalog inside; it never needed to be in the artefact or folder name. A bundle and a git checkout now share the same `<home>` (`~/tksfw`) and the same `codex plugin marketplace add ~/tksfw`.
- The bundle carries `docs/`, `README.md`, `CHANGELOG.md`, `CREDITS.md` and `VERSION` besides the two catalogs and the plugins, so a ZIP user has the guides at hand.
- `ks` resolves a bundle root: `TKSFW_HOME` or `user.toml` may name `~/tksfw` and the plugin inside (`plugins/tksfw`) is found automatically. `docs/getting-started.md`, `docs/distribution.md`, `docs/user-level.md` updated; 2 new tests (250 total). The single-plugin archives (`tksfw-plugin-<v>.zip`, `tksfw-tools-plugin-<v>.zip`) and `tksfw-template-<v>.zip` keep their names.

## [2.3.1] — 2026-09-08

### Fixed
- `ks operator set` / `ks self setup --operator` (via `hooklib.write_operator`) rewrote `~/.config/tksfw/user.toml` and dropped the `home` recorded by `ks self install`; `ks doctor` then warned "user.toml home = not recorded" and `ks` fell back to its script location. Other keys are now preserved.
- `docs/getting-started.md`: the ZIP path was wrong in step 2 (`~/tksfw/tools/ks` does not exist in `tksfw-marketplace-<v>.zip`; `ks` is at `<home>/plugins/tksfw/bin/ks`) and in step 6 (completion script). Rewritten with two explicit choices — source (A: ZIP bundle, B: git checkout; the differences are paths only) and install level (user level / plugin mode, recommended, vs project level / full mode) — with the rationale, and a steps table with one column per source. Mode switching documented as re-initialisation (tested: existing ledgers, plan and agents are kept). 4 new tests (248 total), including an end-to-end `ks self install` from the unzipped marketplace bundle.

## [2.3.0] — 2026-09-08

### Changed
- Human-in-the-Loop default logic is now **OR**: a decision with `Impact ≥ HIGH` **or** `Reversibility ≥ HARD` requires operator confirmation (2.1.0–2.2.1 shipped **and**). Code default (`HIL_DEFAULT`), template `models.toml` `[hil].logic = "or"`, AGENTS.md § Human in the Loop, schemas reference, operations guide and ADR 0012 updated; 2 new tests (244 total).
- Existing projects: `ks project update` refreshes an unmodified `models.toml`; a locally edited one is kept and listed — run `ks hil set --logic or` there (live, no restart). Projects wanting the stricter-to-trigger variant: `ks hil set --logic and`.

## [2.2.1] — 2026-09-07

Documentation pass for the project layers; no code changes.

### Fixed
- Documentation still describing the pre-2.2.0 model: `README.md` (repo tree names `KS_PROJECT.md` / `KS_SPEC.md` and `ks-start`; everyday-commands row for describing and starting a project), `docs/distribution.md` (project layers are user content, not distributed, untouched by `--update`), `template/.agents/hooks/README.md` (`inject_state.py` sections and markers, new `layers.py` row, watched class `layer:l3` / `layer:l4`, Stop-hook row), `plugin-src/tksfw/README.md` (complete skills list), `tksfw-init` skill (no more "AGENTS.md with L3/L4 additions"; `--update` preserves the `layers` stanza; suggest `KS_SPEC.md` on a new project), `register-deliverables` skill (source modes point at L3 `KS_PROJECT.md` / L4 `KS_SPEC.md`).

## [2.2.0] — 2026-09-07

Project layers. L3 (archetype) and L4 (project spec) get a home in the AGENTS.md architecture: a convention, one resolver, a pointer block at session start and an explicit `/ks-start`.

### Added
- Convention for the project layers at the project root: `KS_PROJECT.md` (L3 — what kind of project this is and how such projects run) and `KS_SPEC.md` (L4 — what this project must deliver). Non-mandatory: `ks layers pin --l3 P | --l4 P` declares other paths (`layers` stanza in `.agents/.tksfw.json`, preserved by `ks project update`); L4 alone is valid; both keys may name one file.
- `hooks/layers.py` — the one resolver (arguments → manifest → convention; a declared-but-absent file is `missing`, never a silent fallback) with status `new` / `unchanged` / `changed` / `missing` against a per-host record, optional frontmatter (`ks_layer`, `ks_version`, `title`) validated when present. `ks layers resolve [--l3 P] [--l4 P] [--json] | pin | journal | section`; exit 0 / 3 (nothing) / 4 (missing). `ks project status` layers line.
- SessionStart injects a `<!-- tksfw:layers -->` pointer block (paths + status, ≤ 600 B, never content) on every start, resume and compaction — also on a fresh project without STATE.md; `changed` carries a re-read hint; the hook journals the hashes afterwards.
- L3/L4 are watched inputs (class `layer:l3` / `layer:l4`): PostToolUse journals their edits; the Stop hook and STATE.md report "Project layer edits without a later changes.yaml entry (Layer: ARCHETYPE for L3 / PROJECT for L4)".
- `ks-start` skill (Group A; Claude `/ks-start`, Codex `.codex/prompts/ks-start.md`): resolve → offer to pin argument paths → read L3 then L4 → check precedence → `ks layers journal` → run the L3 start protocol → report. Layer conflicts are `decisions.yaml` entries titled `Layer conflict: …` (no new ledger kind).
- AGENTS.md § Project Layers (L3 / L4): read them in full before planning, re-read *changed* ones, L4 > L3, neither overrides the method. ADR 0013. 30 new tests (243 total).

### Changed
- `inject_state.py` refactored into section emitters + one assembler (`SECTIONS`): `state` (the only truncated section) and `layers` (reserved first), each between `<!-- tksfw:<id> -->` markers; a failing emitter degrades to an error marker instead of failing the injection.
- AGENTS.md: Skill Layering Group B and the Change-Log `Layer` taxonomy now name `KS_PROJECT.md` / `KS_SPEC.md` (legacy `_project-archetype.md` / `_project.md` removed); redundant sentences trimmed (State Snapshot mechanics, Playwright bullets, model-ID rule, shard naming detail, "next prompt confirms", "consider using the skills") to fit the new section — 18,958 B.
- `.codex/prompts/reload-instructions.md` names AGENTS.md / KS_PROJECT.md / KS_SPEC.md. `ks project status`, `ks-completion.sh`, docs (`ks.md`, `getting-started.md`, `operations.md`) updated.

## [2.1.0] — 2026-09-07

### Added
- AGENTS.md § Human in the Loop: decisions at or above the HIL threshold are confirmed by the operator before taking effect (`ConfirmationType: OPERATOR`); Workers never accept them (leave `OPEN`, `main` asks and logs the transition). Default threshold `Impact ≥ HIGH` **and** `Reversibility ≥ HARD`.
- `[hil]` in `models.toml` (`impact`, `reversibility`, `logic`, `mode`); validator `hil_policy/hil_required/hil_problems`, `--hil-ids` (hard failure for new entries in `enforce` mode, WARN otherwise); the PostToolUse hook passes the new decision IDs.
- `ks hil show | set [--impact L] [--reversibility L] [--logic and|or] [--mode enforce|advisory]` — live, validated, with effect line; prompt notice "HIL threshold now … — was …"; `ks doctor` line; digest marks pending HIL decisions "NEEDS OPERATOR CONFIRMATION (HIL)". ADR 0012. 14 new tests (213 total).

### Changed
- AGENTS.md § Task Management 7: the confirmation policy line (previously `HIGH` **or** `HARD`, SHOULD) is now a pointer to § Human in the Loop. 18,959 B.

## [2.0.0] — 2026-09-07

Ledgers as context. Major version: the 2.x line consolidates the project-format changes accumulated since 1.0 (see "Upgrading from 1.x").

### Added
- `yaml-log-entry/assets/digest.py`: deterministic ledger digest — blocked gates (latest REVIEW/TEST/AUDIT/APPROVAL negative with no later positive), decisions in force (effective ACCEPTED), pending decisions, open issues, work in flight (BEGIN without END), recent lessons, recent changes; `--task <T>` view with the task line and evidence chain; `--agent <A>` briefing with the open handoff BEGIN; `--json`.
- STATE.md "Ledger digest" section within `[state].budget_chars` (3,500; whole injection < 9,000 chars), lowest-priority items dropped first with a pointer to `ks ledger digest`.
- `SubagentStart` briefing injected into the subagent (`subagent_track.py --start`): its handoff, task evidence chain, blocked gates, all decisions in force, open issues, recent lessons; `[state].subagent_budget_chars` (4,000).
- Prompt notice: "New open issue …" / "Gate failed: …" when such events are added during the session.
- `ks ledger digest [--task T] [--agent A] [--json]`. `[state]` table in `models.toml`. ADR 0011. 9 new tests (199 total).

### Changed
- AGENTS.md § Task Management: rule 8 "Consult before deciding" (digest before planning/deciding; SUPERSEDED transition before contradicting an ACCEPTED decision; handoff BEGIN lists decision/lesson IDs in `Inputs`); Self-Improvement Loop line points to the digest. 18,858 B.

### Upgrading from 1.x
| Since | Change | What to do |
|---|---|---|
| 1.4.0 | New ledger entries must carry `OwnerSessionId` / `OwnerSessionUserName`; operator name is a per-user item | `ks operator set "<name>"` once per machine; legacy entries stay valid |
| 1.7.0 | Ledgers are partitioned per session (`<ledger>.<token>.yaml`); unsuffixed files are read-only; decisions append-only (status via DECISION events with `DecisionID`); hook state under `.hook-state/hosts/<host>/` | `ks project update`; fold legacy files with `ks ledger archive all --before <today>` when no session is open |
| 1.5.0 | Cumulative archives under `workarea/archive/`; `tasks-archive.md` migrated by `ks ledger archive-plan` | run `ks ledger archive-plan` once |
| 1.9.0 | `ks project reset` and generation records in `.agents/.tksfw.json` | none |
| 2.0.0 | STATE.md carries the digest; subagents receive a briefing; rule 8 | `ks project update`; restart; Codex `/hooks` re-trust; `ks harness retrust --ack` |

2.x compatibility promise: manifest schema (`.agents/.tksfw.json` keys), shard naming, `models.toml` tables (`[tiers] [roles] [routing.*] [delegation] [state]`, `selected`), hook events and their outputs, `ks` verbs and flags, ledger schemas (fields only added as optional, statuses only added). `version_skew()` warns 1.x projects to update.

## [1.9.1] — 2026-09-07

### Fixed
- `ks project reset` (and `ks self setup`) prompted for confirmation whenever stdin was a terminal — including when invoked by the test suite from an interactive shell, where the prompt waited until the 120 s timeout. Prompts now require a terminal on both stdin and stdout; otherwise `--yes` is required. The test harness no longer inherits the terminal's stdin (`stdin=DEVNULL` when no input is given).

## [1.9.0] — 2026-09-07

`ks project reset` — prepare a project to start over.

### Added
- `ks project reset [--archive [--label L]] [--keep-agents] [--registry] [--dry-run] [--yes] [--force]`: clears ledgers (shards + legacy), archives, plan, STATE.md, exports, hook state (all hosts and sessions), work areas, worktrees (+ branches), agent definitions and mirrors; `--archive` moves the durable groups to `.agents/history/<stamp>[-label]/` (faithful snapshot: `workarea/`, `agents/`) and keeps worktree branches. Registry kept by default (`--registry` clears), agents deleted by default (`--keep-agents`). Guardrails: active sessions, `--yes`, unmerged branches, dry run.
- Generation record: `.agents/.tksfw.json` `resets: [{ts, operator, mode, history, …}]`, preserved by `--update`; `hooklib.generation_line()` shown at SessionStart and at the top of STATE.md ("Generation N — reset … previous generation in …").
- `.agents/history/` is never watched. Docs (ks.md, operations.md). 10 new tests (190 total).

## [1.8.0] — 2026-09-07

Excel export of the ledgers.

### Added
- `yaml-log-entry/assets/xlsx_lite.py`: std-lib .xlsx writer (several sheets, bold filled header, frozen header row, autofilter, column widths, wrapped/top-aligned memo cells, real datetimes with number format, IDs as text).
- `yaml-log-entry/assets/export_ledgers.py` and `ks ledger export all | <kind>[,<kind>…] [--out FILE] [--archive] [--session TOKEN] [--csv DIR]`: Summary sheet + one sheet per kind (changes, lessons, handoffs, events, decisions, deliverables, tasks); shards merged, archive optional, extra columns (handoffs Stem/Half, decisions EffectiveStatus, deliverables Present, tasks Agent/Block/Level/Parent, Session/Source/Archived). Default `.agents/workarea/exports/ledgers-<stamp>.xlsx`; CSV fallback.
- `tasks_parse.py` exposes `agent`. Docs (ks.md, operations.md, SKILL.md). 9 new tests (180 total; validated with openpyxl and LibreOffice in the sandbox).

## [1.7.1] — 2026-09-07

### Fixed
- Tool-input paths are matched against the project by real path (`hooklib._rel_input`): on macOS the harness reports `/var/folders/…` while the process cwd resolves to `/private/var/folders/…`, so "named in the tool call" never matched and the READ-ONLY LEDGER rule (foreign shard, legacy file) did not fire under two active sessions. Reproduced with a symlinked `TMPDIR`; the suite now passes in both spellings.

## [1.7.0] — 2026-09-07

Ledgers partitioned per session; per-host hook state — designed for project folders on Box/Dropbox/OneDrive.

### Added
- Session shards `<ledger>.<token>.yaml` for changes, lessons, handoffs, events, decisions: a session writes only its own shards; other shards and the unsuffixed legacy files are read-only (`track_edits.py` → exit 2 "READ-ONLY LEDGER"). All readers merge shards: STATE.md (`hooklib.load_kind`), `cross_check`, `find_entry`, `ks ledger check`, ID index, `archive_ledger` (archives every shard; emptied shards are removed; refuses while sessions are active unless `--force`).
- Decisions append-only: `Status` is the initial status; transitions are `events` of `EventType: DECISION` with the new optional `DecisionID` (validated, cross-checked); STATE.md computes the effective status.
- STATE.md "Sessions (ledger shards)" section; prompt notice "Session K (operator) added N entries: titles".
- `.hook-state/hosts/<hostname>/` for all mutable per-machine state (journal, snapshots, ID index, live subagents, routing journal, lock); `sessions/` stays shared. `TKSFW_HOST` override.
- Sync conflict-copy detection (`changes (1).yaml`, `tasks (conflicted copy).md`, …): SessionStart warning, STATE.md, `ks doctor` (FAIL), `ks ledger check` (fail). `ks doctor` also lists shards and legacy files.
- `new_entry_id.py --stamp` prints the target shard path. ADR 0010. 171 tests.

### Changed
- AGENTS.md § YAML-based Logs: partitioning/ownership rule; § Activity Plan: one plan, one writer session per phase (18,120 B). schemas.md, SKILL.md, hooks README, operations.md updated.
- `MUTABLE_LEDGERS` is now only `deliverables`.

## [1.6.0] — 2026-09-07

Live reconfiguration and a usable installation path.

### Added
- UserPromptSubmit notice (`track_edits.py --phase prompt`): "changed since your last prompt" — routing table/pin, operator, armed flag, `models.toml` edits, and files changed outside the session's tool calls (`ks`, another session, an editor). `hooklib.config_view/config_changes`; the SessionStart hook stores the view the model was shown. Both harnesses accept `additionalContext` on this event.
- `ks`: effect line after every mutating verb (next spawn / next prompt / next session / files); `routing use` refuses while subagents run and `project update` while sessions are active (`--force`); `ks self setup [--operator] [--no-stanza]` — one-shot idempotent user setup (operator, bootstrap stanzas appended to `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`, completion hint); `doctor` checks the stanzas and names the getting-started step for each WARN/FAIL.
- Docs: `docs/getting-started.md` (10 steps, both harnesses, uninstall), `docs/operations.md` (effect timing + procedures: switch routing, update, upgrade, archive, second session, re-trust, running `ks` from inside a session); README "Start here"; AGENTS.md § Tools line on `ks`; hooks README; ks.md "Effects and safety". 12 new tests (166 total).

## [1.5.1] — 2026-09-07

### Changed
- `plugin/` renamed to `plugin-src/` (hand-maintained plugin sources) to stop the one-letter confusion with the generated `plugins/`; `plugins/README.md` added ("GENERATED — do not edit here", with the source → output table); `build_plugin.py`, README, `docs/distribution.md` updated. No functional change.

## [1.5.0] — 2026-09-07

`ks` command line (P0) and cumulative ledger archives.

### Added
- `tools/ks` (stdlib Python, self-locating; shipped as `plugins/tksfw/bin/ks` with `ks-completion.sh`): `self install|version|home`, `operator set|show`, `project init|update|enable|disable|status|drift`, `routing show|check|resolve|use [--clear]`, `ledger check|find|archive-plan|archive`, `harness sync|retrust [--ack]`, `doctor`, `dev build|test|release`. `docs/ks.md`.
- `new_project.py --drift [--json]` (report-only), `route_model.py`: `selected = "<table>"` pin in `models.toml` (after `TKSFW_ROUTING`, before the provider match; validated).
- Archives: `.agents/workarea/archive/<ledger>.yaml` + `archive/tasks.md` (one cumulative, append-only archive per type); classes `archive:<kind>`/`plan-archive`; guard exemption generalised (archive-first move), archives never lose an ID; `cross_check` resolves into archives; `archive_ledger.py` (eligibility: closed history only; migrates `tasks-archive.md`).
- `find_entry.py <ID> [--refs|--prefix|--json]` — entries/tasks across live, archive and plan with reverse references.
- `~/.config/tksfw/trust.json` (hook-hash acknowledgement for `ks harness retrust`); `user.toml` gains `home`.
- ADR 0009; 26 new tests (154 total).

### Changed
- AGENTS.md § Activity Plan "keep it lean" line points to `archive/`; schemas.md § Archives; hooks README; README; user-level.md.

## [1.4.1] — 2026-09-06

The operator name becomes a defined configuration item.

### Added
- `~/.config/tksfw/user.toml` (`schema = 1`, `name = "…"`; directory overridable with `TKSFW_CONFIG_DIR`) as the canonical per-user item; `tools/new_project.py --set-operator "<name>"` writes it, `--show-operator` prints the resolved value and its source (exit 1 when unset); both available from `tksfw-init`.
- `hooklib.operator_source()`; SessionStart reports "(from git config — set it)" when only the fallback resolved. 6 new tests (128 total).

### Changed
- `TKSFW_USER` is documented as an override (CI, one-off shells), `git config user.name` as a reported fallback. Docs: user-level.md, schemas.md, hooks README, README, tksfw-init.

## [1.4.0] — 2026-09-06

Parallel sessions: session token, entry ownership, lost-update guard, session-keyed work areas.

### Added
- Session token (base62-8) minted per harness session by `inject_state.py`, injected with the operator name (`TKSFW_USER` → `~/.config/tksfw/user.toml` → `git config user.name`); heartbeat per hook run; warning when another session is active; records pruned after 24 h.
- Ledger schemas: `OwnerSessionId` / `OwnerSessionUserName` on all six files — required for new entries (`validate_yaml_log.py --require-owner`), accepted absent on legacy entries. `new_entry_id.py --stamp [--session]` prints a ready entry head.
- Lost-update guard in `track_edits.py` (exit 2): EntryID removed from an append-only ledger; another session's entry removed from `decisions.yaml`/`deliverables.yaml`; TaskID removed from `tasks.md` without appearing in `tasks-archive.md`. Project-wide ID index keyed by file hash — catches A-B-A rewrites.
- Per-session snapshots (`hashes.<token>.json`, `ids.<token>.json`) and change attribution `own | external | ambiguous`; external changes never count as unlogged nor as covering entries; Stop hook reports them.
- `workarea.py`: key `<session>.<task>.<instance>` (instance allocated atomically, `< max_parallel_agents`; `--instance` to reuse; `--session` required when several sessions are active); `prune --session`; worktrees use the same key.
- `subagent_track.py` / `route_model.py`: live-subagent cap per session; Stop clears only the own session.
- ADR 0008 (incl. queue evaluation); docs; 21 new repo tests (122 total), skill tests updated.

### Changed
- AGENTS.md: § YAML-based Logs ownership line; § Agent Work Areas key (16,514 → 17,043 B).

## [1.3.0] — 2026-09-06

Activity plan: rules stay in AGENTS.md; grammar and procedure move to `yaml-log-entry`; syntax is hook-enforced.

### Added
- `yaml-log-entry/references/tasks.md`: line grammar, evidence-of-closing rules with the terminal-positive pairs table, archive procedure, harness task-tool note. SKILL.md gains an "Activity plan" section; description covers `tasks.md`.
- `tasks_lint.py`: ERROR (malformed line, unknown status, duplicate TaskID, checkbox/status mismatch) vs WARN (evidence); exit 0/1/2; `--json`.
- `track_edits.py`: lints writes to the live `tasks.md` — errors block (exit 2) with the expected grammar, warnings are advisory; `tasks-archive.md` is never linted.
- `refresh_state.py`: "Archivable plan blocks" hint in STATE.md.
- ADR 0007; 9 new repo tests (101 total) + 1 skill fixture (`warn_tasks.md`).

### Changed
- AGENTS.md § Activity Plan reduced to five rules + pointer (17,715 → 16,514 B).

## [1.2.0] — 2026-09-06

Delegation: decision rules stay in AGENTS.md; mechanics move to a skill; the two limits become hook-enforced.

### Added
- `delegate-work` skill (Group A): `SKILL.md`, `references/isolation.md` (moved method text: worktree vs work area, handoff protocol, cleanup, changing models, persisting agent files), `assets/workarea.py` (`create <agent> <task> [--worktree]`, `list`, `prune <agent> <task> [--force]`, `prune --stale`, `status --json`), 11 skill tests.
- `subagent_track.py` on `SubagentStart`/`SubagentStop` (live-subagent set, cleared at main Stop, 4 h TTL).
- `route_model.py`: denies nested spawns and the (N+1)th live subagent; `[delegation] max_parallel_agents = 4`, `deny_nested_spawn = true` in `models.toml`.
- `check_ledgers_on_stop.py`: "Cleanup reminder" listing stale worktrees/work areas (task COMPLETED / branch merged).
- ADR 0006; 11 new repo tests (92 total).

### Changed
- AGENTS.md § Subagents: procedure lines replaced by pointers to `delegate-work`; § Agent Work Areas reduced to one line (17,998 → 17,715 B).
- `.agents/worktrees/` is never watched by the edit-hash hook.
- `define-agent` gains a Persistence note (moved from AGENTS.md).

## [1.1.0] — 2026-09-06

Install once per user, arm any project from the plugin.

### Added
- `tksfw-init` skill (plugin-only, `plugin/tksfw/skills/tksfw-init/`): the build bundles `template/`, `tools/new_project.py` and `VERSION` as skill assets, so a project can be created (`--plugin-mode` or self-contained), updated, disarmed or re-armed from the installed plugin without a repository checkout.
- Bootstrap stanzas `plugins/tksfw/bootstrap/AGENTS.global.md` (append to `~/.codex/AGENTS.md`) and `CLAUDE.global.md` (append to `~/.claude/CLAUDE.md`): method applies only where `.agents/.tksfw.json` is enabled; elsewhere inert; use `tksfw-init` when asked.
- `docs/user-level.md`; README and distribution updates; 6 new tests.

### Changed
- `tools/new_project.py` detects the skill-assets layout (`template/` next to the script).

## [1.0.0] — 2026-09-06

Safe for user-level deployment: the framework is inert unless a project is armed.

### Added
- `hooklib.armed()` / `guard()`: every hook (`inject_state`, `track_edits`, `check_ledgers_on_stop`, `refresh_state`, `route_model`) exits 0 before touching anything unless `.agents/.tksfw.json` exists with `enabled` ≠ false; legacy in-project layout without manifest stays armed; a plugin instance yields to a project with its own `.agents/hooks/hooks.json`.
- `resolve_project_root()` now reports how the root was found (`env | marker | legacy | cwd`); `cwd` means "no project" and is never armed.
- `inject_state.py`: version-skew warning (project manifest vs installed plugin, major.minor).
- `tools/new_project.py --disable | --enable`; manifest carries `enabled`.
- ADR 0005; hooks README § Arming; 12 new tests (unarmed folder, disabled project, yield, legacy, skew).

## [0.9.0] — 2026-09-05

AGENTS.md is harness-neutral; agent definitions get a neutral source and generated mirrors.

### Added
- `agentlib.py`: `.agents/agents/<name>.toml` → `.codex/agents/<name>.toml` (marker + routed model lines) and `.claude/agents/<name>.md`; managed mirrors (refresh, prune orphans, conflict on hand-made files); used by `track_edits.py` (render after a validated write, prune on delete, advisory `systemMessage` on failure) and by `sync_harness.py --models` (bulk).
- Template directory `.agents/agents/` (replaces `.codex/agents/.keep`).
- ADR 0004.

### Changed
- `AGENTS.md`: `.agents/agents/` replaces `.codex/agents/`; "between sessions, whichever harness"; "harness-native task tools (Codex `update_plan`, Claude Code `TaskCreate`)"; "Playwright/Perplexity MCP tools".
- `hooklib.py`: `AGENTS_SRC`, `AGENT_FILE_RE` → `.agents/agents/`, `MIRROR_PREFIXES` (`.claude/skills/`, `.codex/agents/`, `.claude/agents/`) never watched.
- `define-agent` skill and validator: source path `.agents/agents/`; mirrors are hook-rendered.
- `sync_harness.py --models` delegates to `agentlib`.

### Migration
- `git mv .codex/agents/*.toml .agents/agents/` in existing projects, then `python3 .agents/hooks/sync_harness.py --models`.

## [0.8.0] — 2026-09-05

Agent definitions become a skill-owned, validated procedure.

### Added
- `define-agent` skill: `SKILL.md` (procedure), `references/naming.md` (the former AGENTS.md § Subagents field rules + § Agent Naming, verbatim, with [E]/[W] markers), `assets/validate_agent.py` (name pattern, role ∈ `[roles]`, reserved `main`, harness built-ins refused, filename = name, description prefix, required fields, ≤ 3 tokens, sandbox-by-tier and content warnings, hand-written `model` error in strip mode), `tests/` (10 cases).
- `track_edits.py`: changed `.codex/agents/*.toml` are validated on write; errors block (exit 2) with a pointer to the skill.
- `sync_harness.py --models`: refuses to render an agent file whose rendered text fails validation (reported as conflict).
- `models.toml` `[naming] builtin_agents` (harness built-in names, excluded from the role vocabulary).
- `inject_state.py` preamble: "before creating or renaming any .codex/agents/*.toml, load the define-agent skill".

### Changed
- `AGENTS.md`: § Subagents field block and § Agent Naming reduced to a kernel (pattern, vocabulary = `[roles]` keys, reserved `main`, rename = logged change, load `define-agent`). 20,455 → 17,870 bytes.

## [0.7.0] — 2026-09-05

### Added
- `tksfw-tools` plugin (`plugin/tksfw-tools/` → `plugins/tksfw-tools/`): Perplexity (`@perplexity-ai/mcp-server`) and Playwright (`@playwright/mcp --isolated --output-dir <project>/.playwright`) MCP servers; per-harness definitions (`mcp/codex.json` with `env_vars`, `mcp/claude.json` with `userConfig` keychain option); `check_tools.py` SessionStart prerequisite check.
- Both marketplace catalogs list `tksfw` and `tksfw-tools`; `build_plugin.py` builds/checks/zips every plugin; `docs/mcp-tools.md`.

### Changed
- `plugin/` restructured per plugin (`plugin/tksfw/`, `plugin/tksfw-tools/`).

## [0.6.0] — 2026-09-05

Model selection becomes configuration: tiers in the method, provider tables in `.agents/models.toml`.

### Added
- `template/.agents/models.toml`: `[tiers]`, `[roles]`, `[routing.<provider>]` (ibm + openrouter example), `on_unknown_role`, `codex_agent_files`.
- `route_model.py` PreToolUse hook (`^(Agent|Task)$|spawn_agent`): per-spawn routing via `updatedInput` (`model`, Codex `reasoning_effort`), `additionalContext` with the routed model, deny on unknown role / missing table, `routing.jsonl` journal, `--print` / `--check` / `--resolve`.
- `sync_harness.py --models` (+ `--routing <key>`): renders `model`/`model_reasoning_effort` into `.codex/agents/*.toml` (`inline` or `strip`) and managed `.claude/agents/<name>.md` mirrors (model, effort, read-only tools).
- `inject_state.py`: one-line routing summary at SessionStart.
- `docs/model-routing.md`, ADR 0002; hooks README rows; tests for routing, rendering and mirrors.

### Changed
- `AGENTS.md` § Subagents: model rule rewritten in tier vocabulary; "judge tier" replaces the model name; models change only via `models.toml`.
- `hooklib.py`: `MODELS_TOML` constant.

## [0.5.0] — 2026-09-04

Initial import from the `start-codex` project (Box) into a versioned repository.

### Added
- `template/`: AGENTS.md (19.8 KB, schemas moved to the yaml-log-entry skill), CLAUDE.local.md, `.agents/hooks`, `.agents/skills` (4 Group-A skills), `.agents/workarea/.keep`, `.codex/` (config.toml, prompts, agents).
- Plugin build (`tools/build_plugin.py`) producing one plugin directory with both manifests (`.codex-plugin`, `.claude-plugin`), shared `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}`, and three ZIPs (+ SHA256SUMS).
- Marketplace catalogs at the repo root for Codex (`.agents/plugins/marketplace.json`) and Claude Code (`.claude-plugin/marketplace.json`).
- `tools/new_project.py`: full and `--plugin-mode` instantiation, hash-manifest based `--update`.
- `tests/run_tests.py`: 25 checks (skill suite, build, plugin-mode and in-project hook runs, update semantics, committed-plugin drift).

### Changed
- `hooklib.py`: project root resolved from `$TKSFW_PROJECT_ROOT` / `$CLAUDE_PROJECT_DIR` / walk-up from cwd / legacy file-relative; validator located next to the scripts (plugin) or in the project. Prerequisite for running the hooks from a plugin cache directory.
- `track_edits.py`, `check_ledgers_on_stop.py`: schema/asset paths in messages now come from `hooklib` instead of hard-coded `.agents/skills/...`.
