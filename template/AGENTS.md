# Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Follow the highest standards for your role and your stakeholders.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs/errors.
- **Do NOT fabricate results** that can be calculated. Use a Python script (or scripts) to calculate and validate any result that might be obtained using computational power.
- **Only Quality Sources**: Restrict yourself to recent, relevant, high-quality, and reputable sources.

# Workflow Orchestration Policy

## 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

## 2. Subagent Strategy

- Delegate tasks to subagents to keep context clean and optimize costs and token usage.
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- Separation of duties: Planning, Orchestration and Coordination, Implementation and Validation MUST be done by independent agents.

## 3. Self-Improvement Loop

- After ANY correction from the user, update `lessons.yaml` with the pattern
- After ANY problem, failure, or validation errors: update `lessons.yaml` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until the mistake rate drops
- Review lessons at session start (recent ones are in STATE.md's ledger digest)

## 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would someone more Senior than my role, an upline Manager, or my Customer approve this?"
- Run tests, check logs, demonstrate correctness

## 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

## 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

# Implementation Guidelines

## Agent Behavior Rules

### Subagents

- Before delegating any plan step, check `.agents/agents/` (harness-neutral definitions) for a matching agent by role. The spawn's agent type is the agent's **full name** (`<family>-<role>`), never a bare role or tier — the hook denies spawns of undefined agents.
	- If an existing agent's scope partially matches, update its definition rather than reuse or duplicate.
	- Agent definitions should never carry task history. History lives only in the ledger.
- If none exists, create `.agents/agents/<agent-name>.toml` — **load the `define-agent` skill first** (it owns the field rules, naming and validator; the PostToolUse hook blocks a non-conforming file). Never write `model`/`model_reasoning_effort`: models are routed by **tier** from `.agents/config.toml` (`research` = search/read-only, `build` = implementation, `judge` = planning/judgement/validation); the `-<role>` suffix selects the tier via `[roles]`; the hooks render the model into the harness copies and apply it at every spawn (unknown role → refused).
- Never delegate to the `judge` tier unless the task involves planning or architectural thinking, or judgment/validation.
- Never write a model ID in an agent file or in this document (change procedure: `delegate-work` skill); record the model the hook reports in the Handoff/Event `Model` field.
- Try to constrain each subagent to just one task for focused execution, improved traceability, and optimized handoffs.
- Subagents cannot spawn further subagents — all decomposition happens from the main session only (the routing hook refuses nested spawns).
- Only parallelize subagents when their tasks touch independent files/directories/domains; chain sequentially otherwise.
	- Each subagent must own distinct files/directories; you must NEVER run more than 4 parallel agents per phase (the routing hook refuses the 5th).
	- **Load the `delegate-work` skill** for the mechanics once you decide to parallelise or isolate: git worktree vs agent work area, handoff BEGIN/END, cleanup/prune (the Stop hook reports stale ones).
- For trivial single-file or single-step changes, stay in the main session — delegation overhead isn't worth it.
	- Reserve subagents for tasks that genuinely benefit from isolation, parallelism, or specialization.
- Validation/review subagents must run in a fresh context or worktree, never the implementer's own session.

#### Agent Naming

- Pattern `<family>-<role>`: lowercase, hyphens, ≤ 3 tokens; `<role>` is mandatory and MUST be a key of `[roles]` in `.agents/config.toml` (`planner`, `builder`, `reviewer`, `validator`, `researcher`, `fetcher`, `writer`); `<family>` only to disambiguate. Function, not identity — never names or codenames. Full convention and examples: `define-agent` skill, `references/naming.md`.
- Reserved name `main`: the root session — the only non-subagent and the sole spawner — is `main` in all logs (`AuthorAgent`/`TargetAgent`); no agent definition may use it. When `main` acts as orchestrator it still logs as `main`.
- Names key the Handoff and Event logs (`AgentName`): a rename is a logged change (`changes.yaml`), never a casual edit.

### Task Management

1. **Plan First**: Write plan to `.agents/workarea/tasks.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `.agents/workarea/tasks.md`
6. **Capture Lessons**: Update `lessons.yaml` after corrections
7. **Record Decisions**: Log a `decisions.yaml` entry whenever you make a non-trivial, hard-to-reverse, or architecture-shaping choice — anything a reviewer would later ask "why was it done this way?" about.
	- This is a semantic trigger (like lessons): no hook can detect a missing decision, so it is on you to record it when the choice is made, not reconstruct it later.
	- Confirmation: see § Human in the Loop.
8. **Consult before deciding**: read STATE.md's ledger digest (decisions in force, pending decisions, open issues, blocked gates, work in flight, recent lessons) before planning a phase or recording a decision; `ks ledger digest --task <TaskID>` before working a task. Never contradict an ACCEPTED decision silently: log a `DECISION` event (`Status: SUPERSEDED`) first. A handoff BEGIN lists the decision/lesson IDs the Worker must respect in `Inputs`.

### Human in the Loop
- A decision at or above the **HIL threshold** is confirmed by the operator **before it takes effect** (ask, then `ConfirmationType: OPERATOR`); below it `AUTO-MODE` is allowed and still logged.
- Threshold = configuration: `[hil]` in `.agents/config.toml`, default `Impact ≥ HIGH` **or** `Reversibility ≥ HARD`, `mode = enforce` (a non-compliant new entry is rejected). `ks hil set …` changes it live.
- Workers never accept above-threshold decisions: leave `Status: OPEN` and return; `main` asks the operator and logs the `ACCEPTED` transition. STATE.md marks them "NEEDS OPERATOR CONFIRMATION".

### Tools

- Use the Playwright MCP tools to interact with websites; their temporary files and screenshots MUST live inside the `.playwright` folder.
- Use the Perplexity MCP tools to search and verify data over the internet.
- `ks` (the framework CLI) may be run through the shell tool when the operator asks for an operational change — e.g. `ks routing use <table>`, `ks ledger archive-plan`; such changes are METHOD-layer and logged in `changes.yaml`.

### Skill Layering

- Every skill binds to **exactly one** dependency group and never straddles both:
	- **Group A — policy + method.** Depends only on `AGENTS.md` (L1 + L2). A domain-agnostic mechanism; any archetype/project specifics it needs are passed in as **data**, never hardcoded (e.g. an alias list, a register path, a candidate set). Examples: `yaml-log-entry`, `register-deliverables`, `verify-integrity`, `verify-sources`.
	- **Group B — archetype + project.** Depends only on the project layers `KS_PROJECT.md` (L3) + `KS_SPEC.md` (L4). Examples: `find-questionnaire-sources`, `regenerate-deliverables`, `verify-deliverables`.
- Dependencies point **B → A only.** A Group-B skill MUST NOT restate a policy/method rule; it references it or **calls a Group-A skill** (e.g. `verify-deliverables` calls `verify-integrity`; `find-questionnaire-sources` calls `verify-sources`). A Group-A skill MUST NOT name or depend on any Group-B skill.
- Change-logging is an **ambient** method obligation (always-on memory + the `PostToolUse`/`Stop` hooks); no skill restates "log this change" as a step.
- Because every rule's Source of Truth is an instruction layer (L1–L4), skills are **not standalone**: the relevant layers must travel with them when the skill set is reused elsewhere.

### Other Specifications

#### Project Layers (L3 / L4)

- The session-start block lists the project layers when present: L3 `KS_PROJECT.md` (archetype) and L4 `KS_SPEC.md` (project spec), or the paths pinned under `layers` in `.agents/.tksfw.json`. **Read them in full before planning or executing**; re-read any marked *changed*. L4 overrides L3; **neither overrides this file or the method** — on a conflict follow the method and log a `decisions.yaml` entry titled `Layer conflict: …` (Scope: layer, rule, resolution).
- Start execution as the archetype prescribes with the `ks-start` skill; re-read edited instructions with `ks-reload`. Edits: L3 = `Layer: ARCHETYPE`, L4 = `PROJECT`.

#### Activity Plan

- `.agents/workarea/tasks.md` (Markdown) is the plan: live progress feedback, the resume point between sessions on any harness, and audit evidence. **Load the `yaml-log-entry` skill before writing it** (`references/tasks.md`: line grammar, evidence rules, archive procedure); the PostToolUse hook rejects malformed lines.
- **Ordering:** TaskIDs are random base62 and carry NO order. Sequence and dependency come from document order — top-to-bottom, sub-tasks nested under their parent; the "next" task is the first non-`COMPLETED` item read top-down. Never infer order from IDs or timestamps.
- **One plan, one writer:** `tasks.md` is not partitioned (order is document order). When several sessions share a project, only the session that opened the current phase edits it; another session proposes a task via an `events` entry (`EventType: TASK`, `Status: OPEN`) in its own shard. Sync-service conflict copies (`tasks (1).md` …) are never read — merge by hand.
- **Source of truth:** `tasks.md` is the SoT for tracking, resume and audit. Harness task tools (Codex `update_plan`, Claude Code `TaskCreate`) are an ephemeral in-session aid only — outside `.agents/workarea/` and the audit trail, never a substitute.
- **Evidence of closing:** a COMPLETED leaf task carries `[ev:<EventID>]` citing the `events.yaml` entry that proves it (terminal-positive pairs in the skill) — "never mark complete without proof" is a checkable link; the hook and STATE.md report missing evidence.
- **Keep it lean:** a fully COMPLETED, superseded plan block moves to `.agents/workarea/archive/tasks.md` (`archive_ledger.py plan` / `ks ledger archive-plan`); closed ledger history moves to `archive/<ledger>.yaml` the same way (archive first, then remove — the hook enforces it); only live files are linted.

#### State Snapshot (Resume Entrypoint)

- File: `.agents/workarea/STATE.md` — a compact, **generated** projection of current state (active block, next action, the ledger digest, deliverables built vs pending, last activity, pointers). **Read it first** on resume or after a compaction.
- It is **generated, not hand-edited**: the `Stop` hook rebuilds it at every turn end and the `SessionStart` hook injects it on every start, resume and compaction, from `tasks.md`, the ledgers and the registry. It is a **view, not a Source of Truth**; those files remain authoritative.
- Its fidelity tracks `tasks.md`: keep the plan's statuses current and the snapshot is correct.

#### YAML-based Logs

- Location: `.agents/workarea/`. Each ledger is a YAML **list of single-key mappings** — the entry ID (random base62, 8 chars) is the key, its fields the nested mapping.
- **Authoring rule — before writing or editing ANY `.agents/workarea/*.yaml` file, load the `yaml-log-entry` skill.** It holds the field schemas, enums, formatting rules and canonical examples (`references/schemas.md`), mints IDs and timestamps (`assets/new_entry_id.py` — never invent them) and validates the file. Do not write an entry from memory.
- Ledgers and their triggers (the tooling checks conformance; these rows decide WHEN):

| Ledger | File | Update type | When to log |
| --- | --- | --- | --- |
| Change Log | `changes.yaml` | append-only | Any change to **anything in the workspace** — deliverables and framework/method files alike — classified by `Layer` (see below). Edits to the `.agents/workarea/` bookkeeping files (ledgers, `STATE.md`, `tasks*.md`, the registry) are NOT logged. |
| Decision Log | `decisions.yaml` | mutable (ADR-style) | Every non-trivial, hard-to-reverse or architecture-shaping choice (Task Management §7), when it is made. Edit in place as `Status` evolves; never delete a superseded entry — mark it `SUPERSEDED` and link the successor via `RelatedTo.Decisions`. |
| Lessons Learned | `lessons.yaml` | append-only | After any correction, failure or validation error (Self-Improvement Loop); vet a Worker's `CandidateLessons` and promote the keepers at handoff END; review main-session lessons at session close. |
| Handoff Log | `handoffs.yaml` | append-only | Every subagent delegation: `<stem>-BEGIN` (Orchestrator → Worker, spec + inputs) before dispatch, `<stem>-END` (Worker → Orchestrator, outputs + summary) on return. Each pair is tied to one `events.yaml` entry and one `tasks.md` TaskID. |
| Event Log | `events.yaml` | append-only | Every trackable event — `TASK`, `HANDOFF`, `ISSUE`, `CHANGE`, `DECISION`, `REVIEW`, `AUDIT`, `APPROVAL`, `TEST` — with its typed `Status`. A COMPLETED leaf task cites its terminal-positive event via `[ev:<EventID>]` (Activity Plan). |

- `Layer` (Change Log) reuses the L1–L4 / Group A–B taxonomy, so classification is mechanical: `METHOD` = `AGENTS.md`, Group-A skills, `.agents/hooks/**`, harness config (`.codex/config.toml`, `.claude/settings.json`) — reusable across all projects · `ARCHETYPE` = `KS_PROJECT.md` (the archetype spec), Group-B skills, reusable scaffolding — reusable across instances of this archetype · `PROJECT` = `KS_SPEC.md` (the project spec), the deliverables, instance-specific data — this instance only.
- Enforcement is harness-level, not memory: a `PostToolUse` hook detects writes to the ledgers by content hashing (any tool, shell or script) and blocks a malformed entry, feeding back the validator's report; a `Stop` hook advises when a deliverable/framework edit or a delegation looks un-logged (from the hash journal, never the transcript).
- **Partitioning and ownership:** each session writes only its own ledger shards `.agents/workarea/<ledger>.<session-token>.yaml` (the token is shown at session start); every other shard and the unsuffixed legacy files are read-only, and the hook rejects writes to them. Every new entry carries `OwnerSessionId` and `OwnerSessionUserName` (minted by `yaml-log-entry`). Readers merge all shards; decisions are append-only — a status change is an `events` entry of `EventType: DECISION` with `DecisionID`.

#### Deliverables Registry

- File: `.agents/workarea/deliverables.yaml` — a **mutable manifest** (re-edited when the deliverable set changes; not a ledger, no timestamps). It is the single source of truth for "what is a deliverable" in this project, read by the hooks (deliverable-edit detection), `dod_checks.py` and the `verify-deliverables` skill, so method-bound tooling never hardcodes project naming.
- Populate and refresh it with the `register-deliverables` skill, which owns the schema (alphanumeric `DeliverableID`, `Title` ≤ 80, `Path` = quoted workspace-relative glob or block list of globs, `"<dir>/**"` for folders). `STATE.md` and `tasks*.md` are never registered.

#### Agent Work Areas

- Key `<session-token>.<task-id>.<instance>`: `.agents/workarea/<agent-name>/<key>/` (fallback when git worktrees are unavailable) or `.agents/worktrees/<agent>--<key>/`; created (instance allocated, never chosen by hand) and pruned with the `delegate-work` skill's `workarea.py … --session <token>`. Ledger entries and `tasks.md` status always go to the canonical `.agents/workarea/`, never to a worktree-local copy.

## Execution Guidelines

### Sources, Benchmarks and/or Market References

- Identify sources.
- Explain the rationale and the relevance of the benchmark used.
- For each source, confirm it by looking it up online.
	- If you don't find precise, reliable references, discard them and find an alternative.
	- If you find "mentions" of those sources, but not the source itself, try to find an alternative unless you rate the context of the mention as highly reliable, credible, and without any reputational risk. Otherwise, discard them and find an alternative.
	- Add the URL to the source as part of the reference.
- If you have to find and verify sources, Perplexity.ai is the preferred way to do it.
	- Use a different agent to review/validate search results with a critical point of view.

### Core Output Guidelines

- Use US English for all the outputs.
- Use Markdown for all the deliverables.
- Use Markdown tables over bulletpoints.
- Use Mermaid to represent Architecture diagrams when needed.
- use independent Markdown documents for each deliverable.

## Core Acceptance Criteria

- Evidence of Mermaid diagrams' integrity validation.
- Evidence of JSON integrity validation.
- Evidence of all YAML-based Logs integrity validation.
- Quality Control:
	- Keep deliverables clean: DO NOT add mentions/references to fixes/changes made in the Deliverables themselves.
	- Do NOT leak references to internal working aliases/codenames for inputs into ANY deliverable.
	- Audit trails of (iterative) fixes/changes MUST be added to `changes.yaml`, scoped by `Layer` (METHOD | ARCHETYPE | PROJECT) — framework/method work included, not only deliverable edits.
- The folder is CLEAN of temporary files and folders.
