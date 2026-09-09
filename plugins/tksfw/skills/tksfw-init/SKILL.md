---
name: tksfw-init
description: >
  Initialise, update, arm or disarm the TKS method in the CURRENT project folder from the installed tksfw
  plugin (no repository checkout needed): writes AGENTS.md, CLAUDE.local.md, .agents/workarea/,
  .agents/config.toml, .agents/agents/, .codex/config.toml and the arming manifest .agents/.tksfw.json.
  Use when the user asks to apply/initialise/set up the TKS framework or method in a project, to update a
  project to the installed framework version (SessionStart reports "version skew"), or to disable/enable
  the framework for this project. Never run it unasked: a folder without .agents/.tksfw.json is
  deliberately outside the method.
---

# tksfw-init — instantiate the method in a project

The plugin carries the method template (`assets/template/`) and the installer (`assets/new_project.py`).
Everything it writes is plain files inside the project; the plugin directory itself is never written to.

## Procedure

1. Confirm the target is the project root the user means (the folder that should own `AGENTS.md`).
   If `.agents/.tksfw.json` already exists there, use `--update`, `--disable` or `--enable` — never a
   fresh install.
2. Run, from the plugin (replace `<PLUGIN>` with this skill's parent plugin root — in hooks it is
   `$CLAUDE_PLUGIN_ROOT`; from a skill, use the absolute path of this SKILL.md's `../..`):

   | Goal | Command |
   |---|---|
   | New project, tooling from the plugin (default) | `python3 <PLUGIN>/skills/tksfw-init/assets/new_project.py <project> --plugin-mode` |
   | New self-contained project (hooks + skills copied in-tree; no plugin dependency) | `python3 <PLUGIN>/skills/tksfw-init/assets/new_project.py <project>` |
   | Update to the installed version (keeps locally edited files, lists them) | `… <project> --update` |
   | Disarm / re-arm the framework here | `… <project> --disable` / `--enable` |
   | Set / show the operator name (per user, once; `~/.config/tksfw/user.toml`) | `… --set-operator "<name>"` / `… --show-operator` |
3. Report what was installed / refreshed / kept. Locally edited framework files must be merged by hand —
   show the user the list. The project layers (`KS_PROJECT.md` L3, `KS_SPEC.md` L4, or paths pinned under
   `layers` in `.agents/.tksfw.json`) are the user's content: `--update` never touches them and preserves
   the `layers` stanza. On a new project, suggest writing `KS_SPEC.md` (and `KS_PROJECT.md` when an archetype
   applies); the first session then lists them at start and the `ks-start` skill (`$ks-start` in Codex, `/tksfw:ks-start` in Claude Code) begins execution.
4. Ask the user to re-trust hooks in Codex `/hooks` if the project is self-contained (in-project hooks);
   plugin-mode projects need nothing (the plugin's hooks are already trusted).
5. Log the initialisation or update in `.agents/workarea/changes.yaml` (Layer METHOD) via the
   `yaml-log-entry` skill once the project is armed.

## Notes

- `--plugin-mode` projects contain no hooks/skills of their own; the installed plugin serves them and
  yields automatically to projects that carry their own `.agents/hooks/`.
- A disarmed project (`"enabled": false`) keeps all its files; the hooks and model routing simply
  stop acting there until `--enable`.
- Operator name: ledger entries record `OwnerSessionUserName`. If the SessionStart line shows
  "UNKNOWN" or "(from git config — set it)", run `… --set-operator "<name>"` once on this machine
  (writes `~/.config/tksfw/user.toml`); `TKSFW_USER` overrides it.
- Provider routing: review `.agents/config.toml` after the first install (`[routing.<provider>]` must
  match the provider this machine uses; `route_model.py --print` shows the resolution).
