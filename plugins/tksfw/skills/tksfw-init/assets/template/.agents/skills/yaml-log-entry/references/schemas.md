# YAML ledger schemas — authoritative reference

Source of truth for the **shape** of every file under `.agents/workarea/*.yaml`. `AGENTS.md § YAML-based
Logs` owns the *triggers* (when to log) and points here for the *schemas* (what to write). The
`PostToolUse` hook validates every ledger write against these schemas via `assets/validate_yaml_log.py`,
so a non-conformant entry is blocked at write time. When you extend a schema or enum here, update the
validator **and** add a fixture under `tests/fixtures/` (see `SKILL.md § Tests`).

## Formatting rules (all ledgers)

- Each file is a YAML **list of single-key mappings**: the entry ID is the key, its fields are the nested mapping (this keeps entries foldable in editors).
- Ledger IDs are random base62 strings of 8 characters; Handoff IDs are `<base62-8>-<BEGIN|END>`. Mint them with `assets/new_entry_id.py` — never invent an ID or a timestamp.
- Timestamps use `"YYYY-MM-DD hh:mm:ss"` (quoted). Decisions use `LastUpdate`, every other ledger uses `Timestamp`.
- `Title` fields are at most 80 characters.
- Memo-like fields (any free-prose field that can run long or span lines) MUST use the literal block scalar `|-` so content is preserved verbatim and stays foldable; short single-line fields remain inline; the block body must be indented consistently under its key (4 spaces for fields, 6 for block bodies, as in the examples).
- `Scope` is dual-typed by log: in the Handoff and Event logs it is a short single-line field (≤ 80 chars, inline); in the Decision Log it is a memo (`|-`). Never convert the Handoff/Event `Scope` to a block scalar.
- Lists of IDs or files are **block lists** (one `- item` per line), never flow style `[a, b]` — the pure-Python fallback parser reads block lists only.
- Ensure YAML integrity of each entry before adding it, and of the whole file after adding it (`assets/validate_yaml_log.py`).
- If a log file predates this specification, normalize it deliberately to the schema below before appending; do not run a blind converter that could downgrade an already-conformant ledger.

## Change Log

- File Format: YAML
- Update Type: Append-only
- Location: `.agents/workarea/changes.yaml`
- File Schema:
	- ChangeID: random base62 string of 8 characters.
		- AuthorAgent: Agent name
		- Model: Model name used
		- Timestamp: with format "YYYY-MM-DD hh:mm:ss"
		- Layer: < METHOD | ARCHETYPE | PROJECT > — the scope of the change (see Clarifications and the Layer table).
		- Title: Summarize to a maximum of 80 characters
		- Description: Memo-like field
		- StateBefore: Memo-like field
		- StateAfter: Memo-like field
		- Remarks: Memo-like field
- Example:

```yaml
- 7Kd2Rf9Q:
    AuthorAgent: main
    Model: gpt-5.6-sol
    Timestamp: "2026-07-21 11:05:00"
    Layer: METHOD
    Title: "Add Agent Naming convention to AGENTS.md"
    Description: |-
      Added an Agent Naming subsection under Subagents.
      Split the frontmatter rule so "must start with..." applies to `description`, not `name`.
    StateBefore: |-
      Naming guidance was a single "descriptive and not too long" stub.
    StateAfter: |-
      Full <family>-<role> convention with a role vocabulary and examples.
    Remarks: |-
      Superseded the prior stub to avoid contradiction.
```

- Clarifications:
	- The Change Log records changes to **anything in the workspace**, not only project deliverables. `Layer` classifies the scope so the single ledger stays filterable. This lifts the earlier deliverable-only reading — framework and method work is logged here too.
	- `Layer` reuses the existing L1–L4 / skill Group A–B taxonomy, so classification is mechanical (not a per-change judgment). See the table below.
	- The internal working files under `.agents/workarea/` (the ledgers themselves, `STATE.md`, `tasks*.md`, the deliverables registry) are process bookkeeping, **not** loggable changes — do not create Change Log entries for editing them.

| Layer       | Covers                                                                                                                                                 | Reuse boundary                                  |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| `METHOD`    | `AGENTS.md`, Group-A skills (`yaml-log-entry`, `register-deliverables`, `verify-integrity`, `verify-sources`), `.agents/hooks/**`, `.codex/config.toml`, `.claude/settings.json` | Reusable across **all** projects                |
| `ARCHETYPE` | `_project-archetype.md`, Group-B skills, the reusable `D40-scripts` engine/pipeline scaffolding                                                        | Reusable across instances of **this archetype** |
| `PROJECT`   | `_project.md`, the D-numbered deliverables, instance-specific data/topology/prices                                                                     | **This instance** only                          |

## Decision Log

- File Format: YAML
- Update Type: Mutable log (NOT append-only)
- Location: `.agents/workarea/decisions.yaml`
- File Schema:
	- DecisionID: random base62 string of 8 characters.
		- AuthorAgent: Agent name
		- Model: Model name used
		- LastUpdate: with format "YYYY-MM-DD hh:mm:ss"
		- Title: Summarize to a maximum of 80 characters
		- Description: Memo-like field
		- Rationale: Memo-like field
		- Scope: Memo-like field
		- Impact: < VERY LOW | LOW | MEDIUM | HIGH | VERY HIGH >
		- Reversibility: < TRIVIAL | EASY | MEDIUM | HARD | VERY HARD >
		- Implications: Memo-like field
		- Alternatives: Memo-like field
		- Remarks: Memo-like field
		- ConfirmationType: < OPERATOR | AUTO-MODE >
		- Status: < OPEN | ACCEPTED | SUPERSEDED | DEPRECATED >
		- RelatedTo: OPTIONAL mapping of cross-references — omit the whole field for a decision that stands alone (do not fabricate a link). When present, each sub-key below is itself optional and MUST be a **block list** of IDs (never flow style `[a, b]`); omit a sub-key entirely when there is nothing to relate — do not write an empty list.
			- Tasks: block list of `tasks.md` TaskIDs
			- Decisions: block list of DecisionIDs (self-reference — carries supersede chains)
			- Changes: block list of `changes.yaml` ChangeIDs
			- Lessons: block list of `lessons.yaml` LessonIDs
			- Events: block list of `events.yaml` EventIDs
- Example:

```yaml
- Qv7mK2pL:
    AuthorAgent: planner
    Model: gpt-5.6-sol
    LastUpdate: "2026-07-21 15:00:00"
    Title: "Store records as newline-delimited JSON rather than one array"
    Description: |-
      Persist the record set as newline-delimited JSON (one object per line) instead of a
      single top-level JSON array.
    Rationale: |-
      Append-only writes and line-oriented diffs are cheaper and more robust than rewriting a
      whole array; a truncated write damages one line, not the entire file.
    Scope: |-
      Applies to the on-disk record store only; the in-memory model and public API are unchanged.
    Impact: MEDIUM
    Reversibility: EASY
    Implications: |-
      Readers must parse line-by-line; a one-off migration converts the existing array file.
    Alternatives: |-
      Keep the single JSON array (simpler to read whole, worse to append/diff); use a database
      (a heavier dependency than this project warrants).
    Remarks: |-
      Revisit if records ever need cross-line transactional writes.
    ConfirmationType: AUTO-MODE
    Status: SUPERSEDED
    RelatedTo:
      Tasks:
        - Kp3nR8wQ
      Changes:
        - 7Kd2Rf9Q
- Rt9xN4wB:
    AuthorAgent: main
    Model: gpt-5.6-sol
    LastUpdate: "2026-07-21 16:30:00"
    Title: "Adopt a columnar on-disk format for the record set"
    Description: |-
      Replace the newline-delimited JSON store with a columnar on-disk format.
    Rationale: |-
      Analytical scans over the full record set dominate the workload; a columnar layout reads
      far less data per query than a line-oriented format.
    Scope: |-
      On-disk record store only; supersedes the newline-delimited JSON decision.
    Impact: HIGH
    Reversibility: HARD
    Implications: |-
      Adds a format dependency and a second migration; ad-hoc line inspection is no longer possible.
    Alternatives: |-
      Stay on newline-delimited JSON (simpler, slower scans).
    Remarks: |-
      Operator-confirmed given the higher impact and harder reversibility.
    ConfirmationType: OPERATOR
    Status: ACCEPTED
    RelatedTo:
      Decisions:
        - Qv7mK2pL
      Tasks:
        - Kp3nR8wQ
```

- Clarifications:
	- This log captures the WHY of a choice (ADR-style).
	- Entries are edited in place as a decision's `Status` evolves (`OPEN` → `ACCEPTED` → `SUPERSEDED`/`DEPRECATED`)
	- OPERATOR is used when a human user confirms a decision interactively.
	- AUTO-MODE is used when judgment has been delegated to any agent or the main session.
	- Empty relations are expressed by omitting the `RelatedTo` sub-key, not by an empty or inline list — the pure-Python fallback parser reads block lists only.
- Instructions:
	- Bump `LastUpdate` on every edit.
	- Never delete a superseded entry — mark it `SUPERSEDED` and point the successor back to it via `RelatedTo.Decisions`.

## Lessons Learned

- File Format: YAML
- Update Type: Append-only
- Location: `.agents/workarea/lessons.yaml`
- File Schema:
	- LessonID: random base62 string of 8 characters.
		- AuthorAgent: Agent name
		- Model: Model name used
		- Timestamp: with format "YYYY-MM-DD hh:mm:ss"
		- Title: Summarize to a maximum of 80 characters
		- Description: Memo-like field
		- Remarks: Memo-like field
- Example:

```yaml
- Wq2sL8dH:
    AuthorAgent: validator
    Model: gpt-5.6-sol
    Timestamp: "2026-07-21 11:10:00"
    Title: "Confirm a generated file reproduces before using it as a baseline"
    Description: |-
      An on-disk generated deliverable is a valid regression baseline only if the
      current generator reproduces it byte-for-byte. Otherwise it may be a stale
      artifact from earlier code.
    Remarks: |-
      Verify reproduction first; do not chase a diff against an unreproducible file.
```

- Instructions:
	- Generalize descriptions and remarks when possible.
	- Do NOT generalize if the case is so specific that doing so would eliminate the point of the "Lesson Learned" itself.

## Handoff Log

- File Format: YAML
- Update Type: Append-only
- Location: `.agents/workarea/handoffs.yaml`
- File Schema:
	- HandoffID: <random base62 string of 8 characters>-< HandoffState >.
		- EventID: reference to the corresponding `events.yaml` entry.
		- TaskID: reference to the corresponding `tasks.md` entry.
		- AuthorAgent: Agent name
		- TargetAgent: Agent name
		- Timestamp: with format "YYYY-MM-DD hh:mm:ss"
		- Title: Summarize to a maximum of 80 characters
		- Description: Memo-like field that includes the detailed task specification.
		- Scope: Summarize to a maximum of 80 characters
		- Inputs:
			- Files: array of Fully Qualified Files.
		- Outputs:
			- Files:
				- "N/A" # Value applied on Handoff States "BEGIN".
				- Array of Fully Qualified Files. # Value applied on Handoff States "END".
			- Summary: Summarize to a maximum of 80 characters
			- CandidateLessons: Memo-like field. Provisional lessons surfaced by the Worker; END only ("none" when empty), "N/A" on BEGIN.
- Example:

```yaml
- 3pQ9mK2v-BEGIN:
    EventID: 8sT4wN1c
    TaskID: Kp3nR8wQ
    AuthorAgent: main
    TargetAgent: data-fetcher
    Timestamp: "2026-07-21 11:15:00"
    Title: "Fetch source records for the in-scope set"
    Description: |-
      Retrieve the current records for the in-scope items from the external source API
      (urllib; browser-automation fallback).
    Scope: "In-scope records only; no derived fields."
    Inputs:
      Files:
        - "data/records.json"
    Outputs:
      Files: "N/A"
      Summary: "N/A"
      CandidateLessons: "N/A"
- 3pQ9mK2v-END:
    EventID: 8sT4wN1c
    TaskID: Kp3nR8wQ
    AuthorAgent: data-fetcher
    TargetAgent: main
    Timestamp: "2026-07-21 11:40:00"
    Title: "Fetched source records for the in-scope set"
    Description: |-
      Updated the record set and set the LastUpdated stamp.
    Scope: "In-scope records only; no derived fields."
    Inputs:
      Files:
        - "data/records.json"
    Outputs:
      Files:
        - "data/records.json"
      Summary: "12 records updated; LastUpdated set to 2026-07-21."
      CandidateLessons: |-
        The source API paginates; a single call under-returns.
        Page until the cursor is exhausted, else records are silently missed.
```

- Clarification:
	- A Handoff is bidirectional in nature:
		- At the beginning of a subagent task, we send input information and specifications. This is the Handoff State "BEGIN".
		- At the end of a subagent task, we receive output files and a summary of results. This is the Handoff State "END".
	- HandoffID uniqueness comes from combining two items into a single value. Namely, a "random base62 string of 8 characters" and the "Handoff State" (BEGIN or END).
		- For example: 7Kd2Rf9Q-BEGIN, and 7Kd2Rf9Q-END
		- The first part of the ID binds the two together.
	- For the BEGIN Handoff:
		- The AuthorAgent field is the Orchestrator/Manager agent name or "main" when it is just the "main session".
		- The TargetAgent field is the Worker agent name.
	- For the END Handoff:
		- The AuthorAgent field is the Worker agent name.
		- The TargetAgent field is the Orchestrator/Manager agent name or "main" when it is just the "main session".
	- CandidateLessons carry the Worker's provisional lessons at task end; they are a feeder, not the record. The Orchestrator vets, generalizes, and promotes the keepers to `lessons.yaml` (which stays independent — no HandoffID link). This covers the delegated-work path only; main-session lessons are reviewed at session close, not here.

## Event Log

- File Format: YAML
- Update Type: Append-only
- Location: `.agents/workarea/events.yaml`
- File Schema:
	- EventID: random base62 string of 8 characters.
		- TaskID: reference to the corresponding `tasks.md` entry.
		- AuthorAgent: Agent name
		- Model: Model name used
		- Timestamp: with format "YYYY-MM-DD hh:mm:ss"
		- EventType: < TASK | HANDOFF | ISSUE | CHANGE | DECISION | REVIEW | AUDIT | APPROVAL | TEST >
		- Title: Summarize to a maximum of 80 characters
		- Remarks: Memo-like field
		- Status:
			- For TASKS: < OPEN | COMPLETED >
			- For HANDOFFS: < BEGIN | END >
			- For ISSUES: < OPEN | CLOSED | WORKAROUND | NOT-FIXED >
			- For CHANGES: < OPEN | COMPLETED >
			- For DECISIONS: < OPEN | ACCEPTED | SUPERSEDED | DEPRECATED >
			- For REVIEWS: < OPEN | PASS | FAIL >
			- For AUDITS: < OPEN | CONFORMANT | NON-CONFORMANT >
			- For APPROVALS: < OPEN | GO | NO-GO >
			- For TESTS: < OPEN | OK | KO >
- Example:

```yaml
- 8sT4wN1c:
    TaskID: Kp3nR8wQ
    AuthorAgent: data-fetcher
    Model: gpt-5.6-luna
    Timestamp: "2026-07-21 11:40:00"
    EventType: HANDOFF
    Title: "Data fetch handoff completed"
    Remarks: |-
      Corresponds to handoff 3pQ9mK2v (BEGIN/END).
    Status: END
- 5rB7xC3k:
    TaskID: Ln6vT2yb
    AuthorAgent: validator
    Model: gpt-5.6-sol
    Timestamp: "2026-07-21 12:05:00"
    EventType: AUDIT
    Title: "Conformance sweep"
    Remarks: |-
      Requirements and output-consistency checks verified.
    Status: CONFORMANT
```

## Deliverables Registry (manifest, validated by the same tool)

- File Format: YAML
- Update Type: Mutable manifest (re-edit when the deliverable set changes) — NOT append-only, and it has no `Timestamp`. It is a registry, not a ledger.
- Location: `.agents/workarea/deliverables.yaml`
- Purpose: the single source of truth for "what is a deliverable" in this project. Read by the `Stop` hook (to flag un-logged deliverable edits), `dod_checks.py`, and the `verify-deliverables` skill. This keeps the method-bound tooling free of any project/archetype-specific deliverable naming — the naming lives here, as instance data, and is populated by the `register-deliverables` skill.
- File Schema:
	- DeliverableID: short alphanumeric id, `^[A-Za-z0-9]{1,32}$` (e.g. `REPORT`, `CODE`). No `.`, `_`, or `-`. Folder deliverables still take an alphanumeric id; their folder-ness lives in the `Path` glob.
		- Title: Summarize to a maximum of 80 characters
		- Path: a quoted glob relative to the workspace root, or a block list of quoted globs. Folder deliverables use `"<dir>/**"`. Must be relative (no leading `/`), contain no `..` segment, and not be a bare `*`/`**` catch-all. Block list only (never flow style).
- Example:

```yaml
- REPORT:
    Title: "Final report document"
    Path: "report-*.md"
- CODE:
    Title: "Analysis scripts and data"
    Path: "scripts/**"
```

