# ADR 0010 — Ledgers partitioned per session; per-host hook state (supersedes the level-3 reservation in ADR 0008)

Date: 2026-09-07 · Status: accepted

## Context
ADR 0008 kept "partition instead of serialize" in reserve. The deployment reality changed the analysis:
project folders live in Box (and similar services). Two machines writing one ledger file collide at sync
time, outside any hook, and the service resolves the collision by duplicating the file. No guard on either
machine can see that. The only remedy is to remove the shared write target.

## Decisions
| Choice | Rationale |
|---|---|
| One shard per session per ledger: `<ledger>.<token>.yaml` (changes, lessons, handoffs, events, decisions) | Exactly one writer per file, ever. The write rule becomes trivial and deterministic: own token → write; anything else → read-only (hook rejects). Per-operator or per-machine keys would put two sessions back on one file |
| Unsuffixed `<ledger>.yaml` = read-only legacy shard; `ks ledger archive` folds it into the archive | No migration, nothing rewritten |
| Readers merge everything (STATE.md, cross_check, find, ks ledger check, ID index) | "Seeing what other sessions do" is a read property; STATE.md gains a sessions section, the prompt notice summarises other sessions' new entries |
| Decisions become append-only; transitions are DECISION events with `DecisionID` | A decision created by A cannot be updated in A's shard by B. `EventType: DECISION` already carried the status vocabulary |
| `tasks.md` and `deliverables.yaml` stay single | The plan is one ordered document by design; the registry is project-level. Rule: one plan-writer session per phase; conflict copies detected and never read |
| Owner fields kept | The archive merges shards; `OwnerSessionId` preserves attribution there |
| `.hook-state/hosts/<hostname>/` for mutable state; `sessions/` shared | Journals, snapshots, indices and locks are per machine — the exact files a sync service would duplicate. Shared session records make cross-machine "another session is active" work |
| Sync conflict-copy detection (SessionStart, STATE.md, doctor, ledger check) | Residual duplicates (plan, registry, an unexpected write) become visible instead of silently ignored |
| Still no queue / daemon | Partitioning removes the contention; serialization would add a runtime dependency and still not cover sync-time collisions |

## Consequences
- More files in `.agents/workarea/` (one per session per type); `ls changes.*.yaml`; archiving consolidates and removes emptied shards.
- Existing projects: `--update` brings the new hooks; legacy ledgers stay readable and read-only; `ks ledger archive all` folds them.
- Codex re-trust after update (hook scripts changed).
