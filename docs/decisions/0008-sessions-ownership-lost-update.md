# ADR 0008 — Parallel sessions: session token, entry ownership, lost-update guard (no queue)

Date: 2026-09-06 · Status: accepted

## Context
`<task-id>` keyed agent work areas, which isolates ownership but not concurrency: four instances of one
agent on one task, or two sessions on one project, collide. Beyond work areas, two sessions share the
edit-hash snapshot (changes attributed to the wrong session, or swallowed), the live-subagent cap, and
the ledgers and `tasks.md` themselves (whole-file rewrites by the model → silent lost updates).

## Options considered
| Level | Mechanism | Verdict |
|---|---|---|
| 1 | Detect and attribute: session token, owner fields, per-session snapshots | Adopted |
| 2 | Reject the lost update: ID monotonicity in the PostToolUse hook | Adopted |
| 3 | Partition: per-session ledger shards merged by readers | Reserved — only if parallel sessions become a design target |
| 4 | Serialize: message queue / single-writer daemon | Rejected: the model writes with native harness tools (a queue needs a replacement tool it may bypass), requires a running consumer per project (breaks std-lib-only/no-daemon and harness neutrality; useless across Box-synced machines), and still cannot merge read-modify-write. Contention is a few small text files — optimistic concurrency, not brokering |

## Decision
| Choice | Rationale |
|---|---|
| Session token minted by the SessionStart hook, injected into context | the model cannot know its harness session id; hooks can; base62-8 is path-safe |
| `OwnerSessionId` + `OwnerSessionUserName` on every new ledger entry (operator: `TKSFW_USER` → `~/.config/tksfw/user.toml` → `git config user.name`) | attribution by content, not timing; audit gets who/which session; legacy entries accepted, never rewritten |
| Project-wide ID index keyed by file hash + per-session ID views | lost-update detection independent of any session's diff (A-B-A safe); attribution relative to what each session saw |
| Block rules: append-only ledgers never lose an ID; mutable ledgers lose only own IDs; TaskIDs leave `tasks.md` only into the archive | matches each file's update model |
| Per-session snapshots and change classes `own / external / ambiguous`; ambiguous counts as own | no swallowed edits; advisory reminders may be noisy, never silent |
| Work-area key `<session>.<task>.<instance>`, instance allocated atomically, bounded by `max_parallel_agents` | one source of truth for the cap; no hand-picked numbers |
| Live-subagent cap per session | "per phase" is a session notion |

## Consequences
- Parallel sessions are tolerated and guarded, not designed for; SessionStart says so when it happens.
- A blocked write cannot be rolled back — the message names the entries/tasks to restore.
- Two extra fields per entry; `new_entry_id.py --stamp` prints them. Codex re-trust after update.
