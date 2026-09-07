---
name: ks-start
description: Start executing the current project as its L3/L4 project layers prescribe (KS_PROJECT.md archetype, KS_SPEC.md project spec, or paths declared in .agents/.tksfw.json). Use when the operator asks to begin, kick off, launch, arm or start the project run, or invokes /ks-start.
---

# ks-start — begin execution from the project layers

Group A skill (policy + method): it depends only on `AGENTS.md`; the archetype and project specifics
are read from the L3/L4 files as **data**. It never restates the discovery tiers — `ks layers resolve`
is the one resolver (`python3 .agents/hooks/layers.py resolve` when `ks` is not on PATH; in plugin
mode the script lives under the plugin's `hooks/`).

Loading L3/L4 is automatic (the session-start block lists them). This skill adds the explicit,
deterministic **start**: verify, journal, then run the archetype's start protocol.

## 1. Resolve

Run `ks layers resolve --json` — append `--l3 <path>` / `--l4 <path>` only when the operator passed
paths (tier 1). Read `tier`, `layers[]` (`layer`, `path`, `source`, `exists`, `journal_status`,
`title`) and `warnings[]`.

| Exit / status | Action |
|---|---|
| exit 3 (nothing resolved) | Say so in two lines: `KS_PROJECT.md` / `KS_SPEC.md` at the project root, or `ks layers pin --l3 <p> --l4 <p>`, or pass paths to this skill. Stop. |
| exit 4 (`missing`: declared but absent) | Name the file and the `layers` stanza in `.agents/.tksfw.json`; suggest `ks layers pin --clear` or fixing the path. Stop. |
| any `changed` | Tell the operator which layer changed since the last recorded start and ask whether to proceed before reading further. |
| `warnings[]` non-empty | Report them (frontmatter mismatch, invalid declared path); they do not block. |

## 2. Persist (only when paths were passed as arguments)

Offer once: "Record these paths in `.agents/.tksfw.json` so future sessions resolve them automatically?"
On yes: `ks layers pin --l3 <p> --l4 <p>` (either key alone is fine). That write is a METHOD-layer
change: log it in `changes.yaml`.

## 3. Load

Read L3 (if present) then L4 **in full** with the file tool — the injected block holds pointers, not
content. Summarise in at most six lines: archetype name, deliverables, phases, and the L4 constraints
that narrow L3.

## 4. Check precedence

L4 overrides L3. Neither overrides `AGENTS.md` or the method (ledgers, `tasks.md`, validated writes,
hooks, routing, HIL). If a layer instructs otherwise, **follow the method** and record a
`decisions.yaml` entry (load `yaml-log-entry` first) whose `Title` starts with `Layer conflict:` and
whose `Scope` names the layer (L3/L4), the rule violated and the resolution applied. No new ledger kind.

## 5. Arm

Run `ks layers journal` — records the current hashes so the next session-start reports `unchanged`
or `changed` against this start. Then execute the archetype's start protocol **exactly as written in
L3** (typically: confirm scope with the operator, write the first `tasks.md` block, register the
deliverables with `register-deliverables`, log the kick-off `events.yaml` entry, propose the first task).
If L3 is absent, derive the plan from L4 alone and say so.

## 6. Report

End with one table — layer, file, status, and the first task — plus, only if any were recorded, a
second table of layer conflicts (layer, rule, resolution).

## Notes

- Optional frontmatter in a layer file (`ks_layer: project|spec`, `ks_version`, `title`) is validated
  when present; a mismatch is a warning. Files without frontmatter are fully valid.
- Edits to L3 are `Layer: ARCHETYPE`, to L4 `Layer: PROJECT` in `changes.yaml`; the Stop hook reminds
  you when a layer edit is not covered by a later change entry.
