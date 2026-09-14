# ADR 0016 — Layer model by name: CORE · ARCHETYPE · PROJECT

Date: 2026-09-14 · Status: accepted · Version 3.6.0 · Supersedes the L1–L4 numbering of ADR 0013 (its mechanics stand)

## Context
The framework architecture was consolidated: the former L1 (principles) and L2 (method) are one layer, the
KeelStone **Core** — principles, orchestration policy, agent behaviour, execution guidelines, core acceptance
criteria. In the codebase they had been one file (`AGENTS.md`) since ADR 0013, so the code impact is a
naming pass; the risk sat in the numbers. Renumbering (L3→L2, L4→L3) would give "L2" a new meaning while
every past ledger entry, ADR and changelog line carries the old one.

## Decisions
| Choice | Rationale |
|---|---|
| Layers are named, never numbered: **CORE** (`AGENTS.md`), **ARCHETYPE** (`KS_PROJECT.md`), **PROJECT** spec (`KS_SPEC.md`) | Follows the architecture diagram; no collision with historical numbering; self-describing in ledgers and prompts |
| `changes.yaml` `Layer` enum becomes `CORE \| ARCHETYPE \| PROJECT`; `METHOD` is a read-only alias of `CORE` | Ledgers are append-only — existing entries are never rewritten; the validator accepts `METHOD`, every reader canonicalises it (`hooklib.change_layer`); new entries write `CORE` |
| `PROJECT` keeps its value (not `SPEC`) | It already covers the spec file and the deliverables; renaming it would touch every project's ledgers for no gain |
| Manifest `layers` keys become `archetype` / `spec`; `l3` / `l4` are still read, `ks layers pin` replaces them | No migration step for existing projects; a pin rewrites the stanza with the new keys |
| `ks layers` flags `--archetype` / `--spec`; `--l3` / `--l4` still accepted | Scripts and habits keep working |
| Hook-state classes `layer:archetype` / `layer:spec` | Per-host session state, not shared history — renamed outright |
| The SessionStart pointer block, `ks project status` and `ks help layers` print names ("Archetype", "Spec", "CORE AGENTS.md") | The operator reads the model, not a number |
| ADRs 0001–0015 and the CHANGELOG are not rewritten | History; this ADR is the pointer |

## Consequences
- Kernel `AGENTS.md` § Skill Layering and § Instruction Layers rewritten (18,991 B). No `L1`–`L4` and no `METHOD` remain in the kernel, skills, hooks, tools or guides.
- Existing projects need only `ks project update`; nothing in their ledgers or manifests changes. 7 new tests (322 total).
