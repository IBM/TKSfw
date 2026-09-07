---
name: yaml-log-entry
description: >
  Authoring reference and tooling for the project's YAML ledgers under .agents/workarea/ —
  changes.yaml, lessons.yaml, handoffs.yaml, events.yaml, the mutable decisions.yaml log and the
  deliverables.yaml registry — and for the activity plan tasks.md / tasks-archive.md. LOAD THIS SKILL
  BEFORE writing or editing any of those files: it holds the field schemas, enums, formatting rules and
  canonical examples (references/schemas.md), the tasks.md line grammar, evidence-of-closing rules and
  archive procedure (references/tasks.md), mints unique IDs + timestamps (never invent them), and
  validates the files. Also use it to check ledger integrity after an edit. It does not decide WHEN to
  log (AGENTS.md § YAML-based Logs does) and it does not rewrite legacy files.
---

# YAML ledger authoring + validation

**When** to log is governed by `AGENTS.md § YAML-based Logs` (always in context: the trigger table and
the Layer taxonomy). **What** to write — every field, enum, formatting rule and canonical example — lives
in this skill: read **`references/schemas.md`** before authoring an entry. Enforcement is layered so a
missed skill load is caught, not silently persisted:

| Layer | Mechanism | Guarantee |
|---|---|---|
| Trigger | `AGENTS.md § YAML-based Logs` (always-on) | The when-to-log rules and the "load `yaml-log-entry` first" rule are always present |
| Schema | `references/schemas.md` (this skill) | Single source of truth for field lists, enums, examples; the validator is derived from it |
| Integrity | `PostToolUse` hook → `assets/validate_yaml_log.py` | A malformed ledger write is **blocked** (exit 2) and the problem list is fed back to the model, whichever tool wrote it |
| Completeness | `Stop` hook (advisory) | Flags un-logged deliverable/framework edits and delegations from the hash journal |

The hooks live in `.agents/hooks/` (single source `hooks.json`, mirrored to `.codex/hooks.json` and
`.claude/settings.json` by `sync_harness.py`).

## Procedure for a new entry
1. Read the relevant section of `references/schemas.md` (schema + example for that ledger).
2. Mint the ID and timestamp with `assets/new_entry_id.py` (below); never type them by hand.
3. Append the entry (or edit in place for `decisions.yaml` / `deliverables.yaml`) following the
   example verbatim in shape: single-key mapping, 4-space field indent, `|-` memos, block lists.
4. Validate with `assets/validate_yaml_log.py` (the hook does it too; a failure comes back as the
   tool result — fix it before doing anything else).

## The logs (all under `.agents/workarea/`)
Each file is a YAML **list of single-key mappings** — the entry ID is the key, its fields are the
nested mapping (this is what makes entries foldable). Ledger IDs are 8-char base62; HandoffIDs are
composite `<base62-8>-<BEGIN|END>`. Full field lists, enums, and canonical examples: `references/schemas.md`.

| Kind | File | Update type | ID form |
|---|---|---|---|
| `changes` | `changes.yaml` | append-only | `<base62-8>` |
| `lessons` | `lessons.yaml` | append-only | `<base62-8>` |
| `handoffs` | `handoffs.yaml` | append-only | `<base62-8>-BEGIN` / `<base62-8>-END` |
| `events` | `events.yaml` | append-only | `<base62-8>` |
| `decisions` | `decisions.yaml` | **mutable** (edit in place as `Status` evolves) | `<base62-8>` |

The `deliverables.yaml` **registry** (a mutable manifest, not a ledger; project-alphanumeric IDs, no
timestamp) is validated by the same tool — see the `register-deliverables` skill and
`AGENTS.md § Deliverables Registry`.

## Mint an ID + timestamp — don't invent them
An LLM is a poor RNG and has no authoritative clock, so both are computed and checked unique:
```bash
python3 assets/new_entry_id.py .agents/workarea/changes.yaml           # -> <ID>\t<timestamp>
python3 assets/new_entry_id.py .agents/workarea/handoffs.yaml --handoff BEGIN     # -> <stem>-BEGIN
python3 assets/new_entry_id.py .agents/workarea/handoffs.yaml --handoff END --stem <stem>  # END reuses stem
```
Pass the target file so the new ID is guaranteed absent from it. For a **historical** entry the live
clock is wrong — keep the ID but override the timestamp with the entry's real date (unknown
time-of-day → `00:00:00`, noted in the file header).

## Validate
Runs a whole-file parse **and** per-entry schema check (exact fields, base62 ID, timestamp format,
`Title` ≤ 80, Event `EventType`/`Status` enum pairing, Handoff `Inputs`/`Outputs` shape and BEGIN
`N/A` placeholders, Decision `LastUpdate` format + `Impact`/`Reversibility`/`ConfirmationType`/`Status`
enums + `RelatedTo` block-list shape):
```bash
python3 assets/validate_yaml_log.py .agents/workarea/changes.yaml            # kind inferred from name
python3 assets/validate_yaml_log.py .agents/workarea/handoffs.yaml handoffs   # or pass kind explicitly
```
Exit 0 = valid; exit 1 = problems (printed per entry). The `PostToolUse` hook runs this automatically
on every write to a `.agents/workarea/*.yaml` file, so an invalid entry is caught at write time.

## Cross-ledger integrity + plan lint (multi-file — run in the verify-integrity sweep)
Per-file validity does not prove the *graph* is consistent, and `tasks.md` (Markdown) is not covered
by the per-write validator. Two on-demand checkers close that (both stdlib, both reuse the shared
`assets/tasks_parse.py` — the single `tasks.md` parser):
```bash
python3 assets/cross_check.py                 # R1: resolves FKs across ledgers + tasks.md/archive
python3 assets/tasks_lint.py                   # R2: advisory tasks.md grammar/status/evidence lint
```
- `cross_check.py` — event→task, handoff→event/task + BEGIN/END pairing, decision `RelatedTo`→targets,
  and each COMPLETED task's `[ev:<EventID>]`→a terminal-positive event. **Exit 1 on any dangling FK**
  (open handoffs are WARNs). `--workarea <dir>` points it at a fixture dir.
- `tasks_lint.py` — **advisory** (WARN): line grammar, status/checkbox agreement, duplicate IDs, and
  evidence-of-closing presence on completed **leaf** tasks. Its count also surfaces in STATE.md.

## Tests (the tooling guards every ledger — so it has its own regression suite)
```bash
python3 tests/run_tests.py     # asserts exit codes over committed good/bad fixtures (validator, lint, cross_check)
```
When you extend a schema/enum in `references/schemas.md`, update the validator **and** add a fixture (lesson
`S5PIos9W` — a `TASK`-enum drift slipped through until a fixture caught it).

## Notes
- **`pyyaml`-optional, Python-only.** The validator uses PyYAML when importable, else a targeted
  pure-Python (stdlib) parser for this constrained ledger format. It never shells out to another
  runtime. `new_entry_id.py` is likewise stdlib-only.
- **No legacy upgrade.** This skill does not rewrite non-conformant files. If an old-format log is
  ever encountered, normalize it deliberately on the spot; do not run a blind converter that could
  downgrade a conformant ledger.
- **Scope.** These are internal `.agents/workarea/` ledgers, not `D*` deliverables.

## Activity plan (`tasks.md`)

Grammar, evidence rules and archive procedure: **`references/tasks.md`**. The PostToolUse hook runs
`assets/tasks_lint.py` on every write to the live `tasks.md`: syntactic findings (malformed line,
unknown status, bad timestamp, duplicate TaskID, `[x]` disagreeing with `COMPLETED`) **block** the write
with the expected grammar; evidence findings (COMPLETED leaf without `[ev:…]`) are advisory.
`assets/cross_check.py` resolves `[ev:…]` to a terminal-positive `events.yaml` entry.

| Command | Purpose |
|---|---|
| `python3 assets/new_entry_id.py` | mint a TaskID (same base62 minting as ledger IDs) |
| `python3 assets/tasks_lint.py [tasks.md] [--json]` | exit 0 clean · 1 warnings · 2 errors |
| `python3 assets/cross_check.py` | FK resolution across ledgers and plan (live + archive) |

## Partitioned ledgers (1.7.0)

Write only your own shards: `.agents/workarea/<ledger>.<token>.yaml` (the token is shown at session
start; `assets/new_entry_id.py <ledger> --stamp` prints the exact file). Other sessions' shards and the
unsuffixed legacy files are read-only — the hook rejects writes to them. Read everything: STATE.md,
`cross_check.py`, `find_entry.py` and `ks ledger check` merge all shards. Decisions are append-only: to
change a decision's status, add an `events` entry with `EventType: DECISION`, `DecisionID: <id>` and the
new `Status`. `tasks.md` is one file with one writer session per phase.

## Ownership and parallel sessions (1.4.0)

Every new entry carries `OwnerSessionId` (the session token shown at session start) and
`OwnerSessionUserName` (the operator). `python3 assets/new_entry_id.py <ledger> --stamp [--session <token>]`
prints the entry head with both. The PostToolUse hook requires them on the IDs a write adds and blocks a
**lost update**: any EntryID that disappears from an append-only ledger, an entry owned by another session
that disappears from `decisions.yaml`/`deliverables.yaml`, or a TaskID that leaves `tasks.md` without
appearing in `tasks-archive.md`. On that block: re-read the file, restore the named entries, re-apply your
change. Parallel sessions on one project are tolerated (guarded, attributed), not a design target.

## Finding and archiving

| Command | Purpose |
|---|---|
| `python3 assets/find_entry.py <ID> [--refs]` | locate an entry/task in live ledgers, archives and plan; `--refs` lists everything that references it (TaskID, EventID, RelatedTo, `[ev:…]`) — use it before citing or resolving a cross-reference |
| `python3 assets/archive_ledger.py plan` | move fully COMPLETED, superseded plan blocks to `archive/tasks.md` (STATE.md shows when blocks are archivable) |
| `python3 assets/archive_ledger.py <ledger|all> --before YYYY-MM-DD [--dry-run]` | move closed history to `archive/<ledger>.yaml` (`references/schemas.md § Archives`) — archive first, then remove; the hook enforces that order |

All of these are also reachable as `ks ledger find | archive-plan | archive` (`docs/ks.md`).
