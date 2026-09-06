# ADR 0005 — Arming guard: the framework is inert unless a project opts in

Date: 2026-09-06 · Status: accepted

## Context
Codex plugins are per-user by construction and Claude Code installs plugins at user scope by default, so
the hooks already run in every folder a user opens. `resolve_project_root()` fell back to `cwd`, creating
`.agents/workarea/.hook-state/` in unrelated folders (R1), and a full-mode project plus the installed plugin
ran both hook sets (R4). Codex offers no per-project switch for user-level hooks or plugins.

## Decision
| Choice | Rationale |
|---|---|
| `hooklib.armed()`; every hook calls `guard()` before touching any file | inert by default; nothing is even logged in an unarmed folder |
| Armed = `.agents/.tksfw.json` present and `enabled` ≠ false | one marker, one flag, identical on both harnesses; written by `new_project.py`; `--disable/--enable` toggle it |
| Legacy in-project layout without manifest stays armed | projects created before the manifest existed keep working; `--update` adds the manifest |
| Plugin instance yields to an in-project `.agents/hooks/hooks.json` | a full-mode project pins its version; exactly one layer runs |
| `inject_state.py` reports major.minor skew between manifest and plugin | version drift becomes visible at session start |
| No second switch (env var, config key) | two switches for one state would reintroduce the harness asymmetry |

## Consequences
- User-level deployment becomes safe; per-project disable exists on Codex too.
- Claude Code users may still use `enabledPlugins` as a hard off; the manifest remains the source of truth.
- 1.1.0 adds project instantiation from the plugin (`tksfw-init`) so a folder can be armed without a repo checkout.
