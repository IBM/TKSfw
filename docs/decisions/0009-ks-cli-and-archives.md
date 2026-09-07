# ADR 0009 — `ks` command line (Python, thin dispatcher) and cumulative ledger archives

Date: 2026-09-07 · Status: accepted

## Context
Framework operations were spread over `tools/*.py`, hook flags (`route_model.py --print`), and skill assets.
Ledgers had no archive location except the plan's `tasks-archive.md`, and there was no way to follow an
ID across files.

## Decisions
| Choice | Rationale |
|---|---|
| `ks` in Python (stdlib, ≥ 3.11), not bash or a binary | Python is already the hooks' dependency, so bash buys no dependency saving and costs: macOS `/bin/bash` 3.2, embedded `python3 -` heredocs for every TOML/JSON step, a second test harness. A static binary adds platform builds, signing and a second implementation. A Python script is still an executable text file on PATH |
| Thin dispatcher | No logic duplicated: every verb calls the script that already owns it; `ks` adds only resolution (home, project) and views (status, drift, doctor, retrust) |
| Home resolution order `TKSFW_HOME` → `user.toml home` → own location → plugin dirs; in-project hooks/skills win in full mode | The pinned project version must be what `ks` operates with |
| `routing use` persists `selected` in `models.toml`, after `TKSFW_ROUTING` and before the provider match | A METHOD-layer, logged, per-project choice; the env var stays the per-shell override |
| One cumulative archive per ledger type in `workarea/archive/`, same schema, append-only; move protocol archive-first; guard exemption generalised from `tasks.md` | Single place for history, validator unchanged (`infer_kind` by filename), lost-update guard stays exact |
| Eligibility limited to closed history | STATE.md's open-items view must stay truthful; ACCEPTED decisions are in force and stay live |
| `find` is a script (skill asset), not a skill | Deterministic lookup; the `yaml-log-entry` skill is already loaded when ledgers are in play |
| `retrust` detects, never trusts | Codex trust is interactive; hashes acknowledged via `ks harness retrust --ack` make "re-trust needed" visible |

## Consequences
- 154 tests; `ks` shipped in `plugins/tksfw/bin/`; completion script for zsh/bash.
- `update check/apply` (P1) and `routing pull` (P2) deferred; `routing pull` needs its own ADR (network → trusted config).
