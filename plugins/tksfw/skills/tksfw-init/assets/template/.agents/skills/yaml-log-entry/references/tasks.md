# Activity plan — `tasks.md` (method reference)

Moved from `AGENTS.md` § Activity Plan (1.3.0). AGENTS.md keeps the five rules (location, purpose,
document order, source of truth, evidence link); this file holds the grammar, the evidence details and
the archive procedure. `assets/tasks_parse.py` is the single parser; `assets/tasks_lint.py` checks a
file (ERROR = syntactic, blocks the write via the PostToolUse hook; WARN = evidence, advisory);
`assets/cross_check.py` resolves `[ev:…]` to `events.yaml`.

## File

- Format: Markdown. Location: `.agents/workarea/tasks.md` (live plan); `.agents/workarea/tasks-archive.md`
  (frozen history, never linted).

## Line grammar

```markdown
- [ ] <TaskID> <Title> - <AgentName> : <OPEN|IN-PROGRESS|WAITING-FOR|COMPLETED> <LastUpdateDate: YYYY-MM-DD hh:mm:ss>
	- [ ] <TaskID> <Title> - <AgentName> : <OPEN|IN-PROGRESS|WAITING-FOR|COMPLETED> <LastUpdateDate: YYYY-MM-DD hh:mm:ss> [ev:<EventID>]
	- ...
- ...
```

| Element | Rule (ERROR when violated) |
|---|---|
| `[ ]` / `[x]` | `[x]` if and only if status is `COMPLETED` |
| `<TaskID>` | random base62 (`assets/new_entry_id.py`); unique within the file; carries **no order** |
| `<Title> - <AgentName>` | free text, then ` - `, then the agent (`main` or `<family>-<role>`) |
| `: <STATUS>` | one of `OPEN`, `IN-PROGRESS`, `WAITING-FOR`, `COMPLETED` |
| `<LastUpdateDate>` | `YYYY-MM-DD hh:mm:ss`, the last *recorded* work time |
| Nesting | a tab (or consistent indent) per level; sub-tasks belong to the nearest less-indented task |
| Headings | any `#` heading groups a plan block; the nearest heading names the block in STATE.md |

## Evidence of closing (`[ev:<EventID>]`) — WARN when missing

- A COMPLETED **leaf** task SHOULD carry a trailing `[ev:<EventID>]` citing the `events.yaml` entry that
  proves it. A leaf is a task with no nested sub-tasks; a parent's completion is implied by its leaves.
- The proving event is the one whose `TaskID` matches and whose EventType/Status is terminal-positive:

| EventType | Status |
|---|---|
| `TASK` | `COMPLETED` |
| `REVIEW` | `PASS` |
| `AUDIT` | `CONFORMANT` |
| `APPROVAL` | `GO` |
| `HANDOFF` | `END` |
| `CHANGE` | `COMPLETED` |

- Non-leaf and non-completed tasks carry no `[ev:…]` (WARN otherwise).
- The DoD "never mark complete without proof" is therefore a checkable link: `tasks_lint.py` flags
  presence, `cross_check.py` resolves the ID and the pair rule, STATE.md shows the open count.

## Archive procedure (keep the live plan lean)

1. When a plan block (heading + its tasks) is fully `COMPLETED` and superseded by a newer block, cut
   it from `tasks.md` and append it to `tasks-archive.md`, preserving its order and heading.
2. Leave `tasks.md` holding the current / most recent block(s) only.
3. Integrity checks (`verify-integrity`, the hook) lint the LIVE file; the archive is frozen history
   but stays resolvable by `cross_check.py` for audits.
4. STATE.md notes how many fully COMPLETED blocks the live plan still holds.

## Harness task tools

`tasks.md` is the source of truth. Codex `update_plan` / Claude Code `TaskCreate` are an ephemeral
in-session aid — outside `.agents/workarea/` and the audit trail — and never a substitute.
