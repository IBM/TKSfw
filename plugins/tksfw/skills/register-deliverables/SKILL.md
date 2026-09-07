---
name: register-deliverables
description: >
  Populate or refresh the deliverables registry .agents/workarea/deliverables.yaml — the single
  source of truth for "what is a deliverable" in this project, read by the Stop hook and the
  project's deliverable-aware verification tooling. Extract the deliverable set from an archetype
  spec doc, a project spec doc, or an interactive conversation, then write and validate it. Use at
  project setup, or whenever the deliverable set changes (added/removed/renamed).
---

# Register deliverables

Build `.agents/workarea/deliverables.yaml` so the method-bound tooling can detect deliverable edits
without hardcoding any naming scheme. The registry is a **mutable manifest** (re-edited when the set
changes) — NOT an append-only ledger. This skill owns the schema (below and in
`../yaml-log-entry/references/schemas.md § Deliverables Registry`); `AGENTS.md § Deliverables Registry`
states its purpose and that it is populated here.

This skill is **archetype-agnostic**: it works on *any* deliverable-listing source. The IDs, titles,
and paths come entirely from the source you point it at — nothing about a specific `D<nn>` scheme is
baked in. The only fixed output is the registry *shape*, which is validated deterministically.

## Source modes (pick what applies)
| Mode | Input | How |
|---|---|---|
| Archetype doc (L3) | `KS_PROJECT.md` (or the L3 path from `ks layers resolve`) DELIVERABLES section | Read the doc; extract each deliverable's ID, title, and file/folder path. |
| Project doc (L4) | `KS_SPEC.md` (or the L4 path) mission/deliverables list | Same, from the project-specific list; L4 narrows or extends L3. |
| Interactive | live conversation | Ask the user for the deliverable set (or confirm a proposed one) and record it. |

## Entry schema (minimal)
Each entry is a single-key mapping — the deliverable ID is the key (IDs shown are illustrative;
use the project's own):
```yaml
- REPORT:
    Title: "Final report document"
    Path: "report-*.md"
- CODE:
    Title: "Analysis scripts and data"
    Path: "scripts/**"
```
Authoring rules (enforced by the validator — get them right up front):
- **ID**: alphanumeric only, `^[A-Za-z0-9]{1,32}$` (no `.`, `_`, or `-`). A folder deliverable still
  gets an alphanumeric ID; its folder-ness lives in the `Path` glob.
- **Title**: ≤ 80 characters.
- **Path**: a **quoted** glob (or a block list of quoted globs) relative to the workspace root.
  Quote it — an unquoted leading `*` is a YAML alias and breaks parsing. Use `"<dir>/**"` for a
  folder deliverable. No leading `/`, no `..` segment, no bare `*`/`**` catch-all. Block list only
  (never flow style `["a","b"]`). Indent fields 4 spaces.

## Procedure
1. Read the chosen source doc (or elicit interactively) and extract, per deliverable: ID, Title, Path.
2. Write `.agents/workarea/deliverables.yaml` with a header marking it a REGISTRY and the entries above.
3. **Validate** (the PostToolUse hook also does this automatically on write):
   ```bash
   python3 ../yaml-log-entry/assets/validate_yaml_log.py .agents/workarea/deliverables.yaml deliverables
   ```
   Fix any reported problem (bad ID, Title > 80, non-relative/`..`/bare-glob Path, missing field).

## Notes
- Re-run this skill whenever deliverables are added, removed, or renamed — the registry is the one
  place all tooling consults, so keeping it current keeps the Stop hook and every deliverable-aware
  check accurate.
- Do not leak project/prompt aliases into `Title`s that might surface in reports; keep titles plain.
