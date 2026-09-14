---
name: ks-reload
description: Reload the instruction layers (AGENTS.md core, the archetype and the project spec) fresh from disk after the operator has edited them. Use when the operator says the instructions, AGENTS.md, KS_PROJECT.md or KS_SPEC.md changed, or invokes ks-reload.
---

# ks-reload — re-read the instruction layers

Group A skill (method only). Use it after the operator has edited `AGENTS.md` or a project layer during a
session; the auto-loaded copy in context is stale from that moment.

1. Run `ks layers resolve --json` to see which layer files resolve and which are marked *changed*.
2. Re-read **from disk**, in this order and in full: `AGENTS.md` (Core), then the Archetype (`KS_PROJECT.md` or the
   declared path), then the Spec (`KS_SPEC.md` or the declared path). Do not rely on what was injected at session start.
3. State briefly what changed versus your prior understanding (which sections, what the new rule is). Precedence is
   unchanged: Spec overrides Archetype; neither overrides `AGENTS.md`. If a layer contradicts `AGENTS.md`, say so and follow
   `AGENTS.md`.
4. Run `ks layers journal` so the next session start compares against the version you just read.
5. Continue the task under the reloaded instructions. If the operator changed the method itself (`AGENTS.md`), the
   edit is logged in `changes.yaml` with `Layer: CORE`; archetype edits are `ARCHETYPE`, spec edits `PROJECT`.
