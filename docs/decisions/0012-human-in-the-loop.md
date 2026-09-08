# ADR 0012 — Human in the Loop: a configurable, hook-enforced confirmation threshold

Date: 2026-09-07 · Status: accepted

## Context
Until 2.0 the confirmation policy was one SHOULD line under "Record Decisions" (`Impact ≥ HIGH` **or**
`Reversibility ≥ HARD` → `OPERATOR`) with nothing checking it. The operator wants the rule explicit, the
default stricter (both conditions), and the threshold changeable during a session.

## Decisions
| Choice | Rationale |
|---|---|
| Rule in AGENTS.md § Human in the Loop; threshold in `models.toml` `[hil]` (`impact`, `reversibility`, `logic and|or`, `mode enforce|advisory`) | The rule is method (static); the threshold is configuration (live) — same split as model routing |
| Default `Impact ≥ HIGH` **or** `Reversibility ≥ HARD`, `enforce` (2.3.0; 2.1.0–2.2.1 shipped **and**) | Operator's requirement after use: a high-impact call that is easy to undo and a hard-to-undo call of modest impact both deserve a human; `ks hil set --logic and` restores the stricter-to-trigger variant |
| Enforcement in the validator (`hil_problems`), applied as a hard failure only to **new** decision entries (`--hil-ids`, passed by the PostToolUse hook); existing entries produce WARN lines in `ks ledger check` | Legacy ledgers stay valid; the check bites where it can be acted on — at write time |
| Two violations: above-threshold entry without `ConfirmationType: OPERATOR`; above-threshold entry authored by a non-`main` agent with `Status ≠ OPEN` | Workers escalate, `main` asks the operator and logs the `ACCEPTED` transition as a DECISION event |
| What is not verified: that a human actually confirmed | Not observable from the ledger; `OPERATOR` is the agent's attestation, the harness's ask-the-user tool is the mechanism, and the entry is auditable |
| `ks hil show|set` rewrites `[hil]` in place, validates values and TOML, prints the effect line; the prompt notice reports "HIL threshold now … — was …" | Hot update through the existing configuration-view mechanism; no restart |
| Digest marks OPEN above-threshold decisions "NEEDS OPERATOR CONFIRMATION (HIL)" in STATE.md and in subagent briefings | A Worker sees what it must not decide |

## Consequences
- AGENTS.md 18,959 B (new section; §7 policy line replaced by a pointer; three redundant sentences removed elsewhere).
- 14 new tests (213 total). `ks doctor` prints the effective threshold.
