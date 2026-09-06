# Agent definitions — fields and naming (method reference)

Moved verbatim from `AGENTS.md` § Subagents / § Agent Naming (0.8.0). `AGENTS.md` keeps only the
kernel: the `<family>-<role>` pattern, "role = a key of `[roles]` in `.agents/models.toml`", the
reserved name `main`, "a rename is a logged change", and the rule to load this skill before
creating or renaming any `.agents/agents/*.toml`. `assets/validate_agent.py` enforces everything
marked **[E]** (error, blocks the write) and reports everything marked **[W]** (warning).

## Definition file — `.agents/agents/<agent-name>.toml`

- Before delegating any plan step, check `.agents/agents/` for a matching agent by role.
  - If an existing agent's scope partially matches, update its definition rather than reuse or duplicate.
  - Agent definitions never carry task history. History lives only in the ledger.
- Proper TOML key-value syntax. Keys Codex documents for custom agents: `name`, `description`,
  `developer_instructions` (required), `model`, `model_reasoning_effort`, `sandbox_mode`,
  `mcp_servers`, `skills`, `model_instructions_file`, `nickname_candidates`. Other keys **[W]** — Codex
  may reject unknown keys.
  - `name` **[E]**: follows the naming convention below; the filename stem must equal `name`.
  - `description` **[E]**: must start with "Use PROACTIVELY when..." or "MUST BE USED for...". It
    drives selection; put selection detail here, not in the name.
  - `developer_instructions` **[E non-empty; W content]**: must include explicit scope, relevant
    file paths, and success criteria — never vague instructions like "implement the feature."
    Request structured, concise summaries back; avoid dumping raw output into main context.
  - `sandbox_mode` **[W]**:
    - `read-only` for read-only roles (researcher, reviewer, validator, planner)
    - `workspace-write` for writing roles (builder, writer, fetcher — a fetcher writes what it fetches,
      although it runs on the `research` tier)
  - `model` / `model_reasoning_effort`: NEVER hand-written. The tier is derived from the role (or a
    `# tksfw-tier: <tier>` comment) and rendered into the Codex mirror from `.agents/models.toml`. With `codex_agent_files = "strip"` a literal `model` line is an error **[E]**;
    with `"inline"` a line that does not match the current routing is a warning **[W]** (it will be rewritten).
- Persist agent files in the repo so they are reused across sessions, not recreated each time.
- Harness mirrors — `.codex/agents/<name>.toml` (Codex) and `.claude/agents/<name>.md` (Claude Code) —
  are generated from the source by the hooks (`agentlib.py`); never edit them by hand. The source
  directory `.agents/agents/` is the only harness-neutral location and the only one AGENTS.md names.

## Agent Naming

- Name agents by **function, not identity** — a name is a job title on the roster, not a person.
  Never use human names or opaque codenames; they carry no meaning for the reader or for
  auto-delegation and pollute the audit ledger.
- Pattern: `<family>-<role>` — kebab-case, lowercase, hyphen-separated **[E]**.
  - `<role>` is the head noun and is mandatory; it states what the agent does **[E]**.
  - `<family>` is an optional domain/subsystem prefix. Include it ONLY when more than one family is
    in scope or names would otherwise collide; omit it when every agent would carry the same prefix.
  - Use full, plain words — never truncations or acronyms (`pricing-reviewer`, not `prc-rvw`).
    "Short" means one clear word, not an abbreviation. Tokens shorter than 3 letters **[W]**.
- Draw `<role>` from a closed, reused vocabulary so the fleet reads as one taxonomy. The vocabulary
  is the set of keys of `[roles]` in `.agents/models.toml` (currently `planner`, `builder`,
  `reviewer`, `validator`, `researcher`, `fetcher`, `writer`) **[E]**; harness built-in agent names
  listed under `[naming] builtin_agents` are not method roles **[E]**.
  - Extend this list deliberately (edit `[roles]`, a METHOD change); do not invent a one-off role
    word per agent.
- Order `<family>` first so related agents sort and scan together (`pricing-fetcher`, `pricing-validator`).
- The `name` is a stable identifier; the `description` drives selection.
  - Names are keyed by the Handoff and Event logs (`AgentName`); treat a rename as a logged change
    (`changes.yaml`), never a casual edit, to preserve audit continuity.
- Constraints: lowercase letters and hyphens only; unique within `.agents/agents/` **[E]**; descriptive
  but not long (2 tokens target, 3 ceiling **[E]**).
- Reserved name — `main` **[E]**: the root session (the only non-subagent, and the sole entity that
  may spawn subagents) is named `main` in all logs (`AuthorAgent`/`TargetAgent`).
  - This is a deliberate exception to "function, not identity": the main session is a structural
    singleton with no peers to disambiguate against, so an identity name is correct.
  - `main` is a role, not an agent definition: never create `.agents/agents/main.toml`, and no
    subagent may take the name.
  - `main` names the *identity*; "Orchestrator/Manager" names a *role* that either `main` or a
    delegated coordinator agent may hold. When the main session acts as orchestrator, it still logs
    as `main`, not a separate role name — reserve a distinct agent name only for a coordinator you
    actually delegate to.
- Examples:
  - Good: `report-builder`, `index-builder`, `data-fetcher`, `output-validator`, `sources-researcher`.
  - Good (bare role, single family): `planner`, `reviewer`.
  - Reserved: `main` (the root session; not a subagent — see above).
  - Avoid: `project-agent-1` (non-functional), `src-fch` (truncated), `atlas` (codename),
    `end-to-end-output-conformance-reviewer` (too long).
