---
name: verify-integrity
description: >
  Run the method-level integrity and hygiene sweep for any project — independent of what the
  deliverables mean. Validates the YAML process logs, checks Mermaid-diagram and JSON integrity,
  scans outputs for internal-alias leakage, and confirms a clean workspace, per
  AGENTS.md § Core Acceptance Criteria. Use before hand-off, after edits to logs or generated
  artifacts, or whenever "is everything structurally sound?" must be answered. Domain-agnostic
  (no deliverable/ARR/catalog knowledge); a domain conformance sweep can call it for integrity
  evidence.
---

# Verify integrity (method sweep — Group A)

The **policy+method** half of QA. It enforces `AGENTS.md § Core Acceptance Criteria`, which are the
same for every project regardless of domain: **logs, diagrams, and data files are structurally
valid; no internal alias leaks into outputs; the workspace is clean.** It knows nothing about
D-numbers, ARR, capacity, or catalogs — those belong to a domain conformance sweep (Group B), which
calls this skill for the integrity evidence its conformance record needs.

## Checks

### 1. YAML process logs valid (logs are not deliverables)
Validate every `.agents/workarea/` log with the **yaml-log-entry** validator (the `PostToolUse` hook
also does this on write):
```bash
for f in changes lessons handoffs events decisions deliverables; do
  python3 ../yaml-log-entry/assets/validate_yaml_log.py .agents/workarea/$f.yaml
done
```

### 1a. Cross-ledger referential integrity (graph consistency)
Per-file validity does not prove the graph is consistent. Resolve the foreign keys across files —
event→task, handoff→event/task + BEGIN/END pairing, decision `RelatedTo`→targets, and each COMPLETED
task's `[ev:<EventID>]`→a terminal-positive event. **Fails (exit 1) on any dangling reference:**
```bash
python3 ../yaml-log-entry/assets/cross_check.py
```

### 1b. Activity-plan lint (advisory)
Lint `tasks.md` grammar, status/checkbox agreement, duplicate IDs, and evidence-of-closing presence
on completed leaf tasks. **Advisory** — review the WARNs (they also surface as a count in STATE.md);
they do not block the sweep:
```bash
python3 ../yaml-log-entry/assets/tasks_lint.py   # exit 1 if issues; treat as advisory
```

### 2. Mermaid integrity
Render each Mermaid diagram with `@mermaid-js/mermaid-cli` (`mmdc`) — it must parse/render without
error. Capture the result as evidence.
```bash
mmdc -i <file-with-mermaid>.md -o "$TMPDIR/mmd-check.svg" && echo "mermaid OK"
```

### 3. JSON integrity
Every JSON artifact must parse:
```bash
python3 -c "import json,sys; [json.load(open(p)) for p in sys.argv[1:]]; print('json OK')" <file.json> ...
```

### 4. No internal-alias leakage + clean folder (mechanical helper)
The *rule* is method; the *alias strings* are instance data — the caller supplies them (a Group-B
sweep reads them from its project's inputs and passes them here). This skill never hardcodes them:
```bash
python3 assets/integrity_checks.py --aliases <ALIAS1> <ALIAS2> ... --require-aliases   # + clean-folder scan
```
`integrity_checks.py` discovers the document deliverables from `.agents/workarea/deliverables.yaml`
(registry; legacy `D*.md`/`D*.yaml` fallback) and confirms none contain any supplied alias, then
walks the tree for `__pycache__`, `.DS_Store`, `*.pyc`, `*.tmp`, and Office lock files (`~$…`).
Scan an explicit set instead with `--files a b …`.

**`--require-aliases`:** because the aliases are caller-supplied data, an empty list makes the
leak check a silent no-op. Pass `--require-aliases` whenever the project is known to have internal
aliases: an empty list then **FAILS (exit 1)** instead of skipping. Without the flag, an empty list
emits a visible **WARN** and passes — the lenient default for a genuinely alias-free project.

## Output
A pass/fail per check. Return the evidence to the caller (e.g. a Group-B conformance sweep) for its
conformance record — this skill produces the evidence, it does not own the conformance deliverable.

## Notes
- **Group A only.** This skill binds to policy + method (`AGENTS.md`), never to the archetype or
  project. The alias list and the deliverable file set are *data* it receives, not dependencies.
- Std-lib only; `mmdc` needs `@mermaid-js/mermaid-cli`.
