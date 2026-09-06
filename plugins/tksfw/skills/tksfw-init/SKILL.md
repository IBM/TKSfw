---
name: tksfw-init
description: >
  Initialise, update, arm or disarm the TKS method in the CURRENT project folder from the installed tksfw
  plugin (no repository checkout needed): writes AGENTS.md, CLAUDE.local.md, .agents/workarea/,
  .agents/models.toml, .agents/agents/, .codex/config.toml and the arming manifest .agents/.tksfw.json.
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
3. Report what was installed / refreshed / kept. Locally edited files (typically `AGENTS.md` with L3/L4
   additions) must be merged by hand — show the user the list.
4. Ask the user to re-trust hooks in Codex `/hooks` if the project is self-contained (in-project hooks);
   plugin-mode projects need nothing (the plugin's hooks are already trusted).
5. Log the initialisation or update in `.agents/workarea/changes.yaml` (Layer METHOD) via the
   `yaml-log-entry` skill once the project is armed.

## Notes

- `--plugin-mode` projects contain no hooks/skills of their own; the installed plugin serves them and
  yields automatically to projects that carry their own `.agents/hooks/`.
- A disarmed project (`"enabled": false`) keeps all its files; the hooks and model routing simply
  stop acting there until `--enable`.
- Provider routing: review `.agents/models.toml` after the first install (`[routing.<provider>]` must
  match the provider this machine uses; `route_model.py --print` shows the resolution).
