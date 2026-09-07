# ADR 0013 — Project layers L3/L4: convention, one resolver, pointer injection, `/ks-start`

Date: 2026-09-07 · Status: accepted

## Context
Before Codex support, L3 (project archetype) and L4 (project details) were inlined into the Claude Code
prompt through `@` inclusion in `CLAUDE.local.md` (`@_method.md`, `@_project-archetype.md`,
`@_project.md`). With `AGENTS.md` as the shared kernel (L2 folded in, iterated down to always-on
triggers) the L3/L4 layers had no home: `@` inclusion is Claude-only, unbounded in size, and not
compaction-safe. Functional area 1 — direct use of L3/L4 content — needs a shape that is open and
flexible; remote libraries and their distribution (areas 2 and 3) are roadmap.

## Decisions
| Choice | Rationale |
|---|---|
| Recommended, non-mandatory convention: `KS_PROJECT.md` (L3, the archetype) and `KS_SPEC.md` (L4, the project spec) at the project root | L3/L4 are the user's content; the framework owns discovery and hand-off, not the files. `KS_` matches the `ks` CLI; uppercase root files sit next to `AGENTS.md` and `STATE.md` where humans and agents look first. "Project" was preferred over "archetype" for end-user clarity; the optional frontmatter `ks_layer` disambiguates once library-sourced L3 exist |
| One resolver, three tiers, in `hooks/layers.py`: arguments → `layers` stanza in `.agents/.tksfw.json` → convention; a declared-but-absent path is `missing`, never a silent fallback; L3 optional; both keys may name one file | "Ad-hoc" is not "outside the framework": a declared path gets everything the convention gets (hashing, drift, injection, `/ks-start`). Every consumer (SessionStart hook, `ks-start` skill, `ks layers`, later `ks go`) calls the resolver; none restates the tiers |
| Automatic loading = one kernel section in `AGENTS.md` + a pointer block from the SessionStart hook (paths, status; ≤ 600 B; never content or hashes) | Identical in both harnesses; re-injected on start/resume/compaction; bounded regardless of file size; the model reads the files with its file tool |
| Status against a per-host record (`layers.json`): `new` / `unchanged` / `changed` / `missing`; the hook and `ks layers journal` (called by `/ks-start`) write the baseline | `changed` is the drift signal that forces a re-read instead of trusting stale context. Same hash algorithm as the journal (`sha256_file`) |
| L3/L4 are watched INPUTS: class `layer:l3` / `layer:l4`, journaled by PostToolUse, reported by the Stop hook and STATE.md as "Project layer edits … (Layer: ARCHETYPE for L3 / PROJECT for L4)" | Mid-run edits to the spec are exactly the drift an operator wants flagged; the taxonomy in AGENTS.md already maps L3 → ARCHETYPE, L4 → PROJECT |
| Precedence: L4 overrides L3; neither overrides L2/L1. A conflict is logged as a `decisions.yaml` entry titled `Layer conflict: …` (Scope: layer, rule, resolution) — no new ledger kind | A new kind would touch the validated schema, the hook validator, the skill and its tests for a rare event; a Title prefix is greppable and schema-neutral |
| `ks-start` skill (Group A, in the core plugin; Codex prompt `/prompts:ks-start` and Claude `/ks-start`) = the explicit start: resolve → (offer `pin` when paths were passed) → read L3 then L4 → check precedence → `ks layers journal` → run the L3 start protocol → report | Loading is automatic and silent; starting is user intent and deterministic. Separating the two means a user who never types `/ks-start` is still correctly briefed |
| SessionStart payload refactored into emitters + assembler (`SECTIONS` in `inject_state.py`): `state` (truncated to fit) and `layers` (reserved first), each between `<!-- tksfw:<id> -->` markers; a failing emitter degrades to an error marker | The hook was already accreting lines; a third section (routing table, agent roster) becomes a one-file addition; golden tests can assert each section |
| `ks go` (headless launch/validation), remote libraries, mandatory frontmatter for library-sourced L3 | Deferred — roadmap (areas 2 and 3) |

## Consequences
- New: `hooks/layers.py`, `ks layers resolve|pin|journal|section`, `ks project status` layers line,
  `skills/ks-start/SKILL.md`, `.codex/prompts/ks-start.md`; `new_project.py --update` preserves the
  `layers` stanza; `.codex/prompts/reload-instructions.md` names the new files.
- AGENTS.md § Project Layers (L3 / L4); Skill Layering Group B and the Change-Log `Layer` taxonomy name
  `KS_PROJECT.md` / `KS_SPEC.md`; redundant sentences trimmed elsewhere to keep the kernel at 18,958 B
  (< 19,000). Legacy `_project-archetype.md` / `_project.md` references removed.
- A fresh project with layer files now receives a SessionStart injection (the layers block) even
  before STATE.md exists; a project without layers is unchanged.
- 30 new tests (243 total).
