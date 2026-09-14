# ADR 0017 — ks output conventions: one renderer, semantic colour, plain and JSON for machines

Date: 2026-09-14 · Status: accepted · Version 3.7.0

## Context
`ks` grew verb by verb; each printed in its own shape (`key : value`, `== section`, `ok/WARN/FAIL`, bracketed
tags). Ahead of an open-source release the CLI must read as one product, stay dependency-free, and remain safe
for the two non-human readers of its output: shell pipelines and the model (hooks and skills call `ks`).

## Decisions
| Choice | Rationale |
|---|---|
| One renderer class in `tools/ks` (`header`, `section`, `kv`/`flush`, `table`, `finding`, `hint`, `die`) | Every screen conforms by construction; ~150 lines, standard library |
| Colour is semantic (green ok, yellow attention, red refused, cyan identifiers/commands, dim context), bold for section titles and the thing that changed; no emoji | Colour marks meaning so a screen without yellow/red needs no reading; emoji have inconsistent widths |
| Colour only when stdout is a TTY, `NO_COLOR` unset, `TERM != dumb`, no `--no-color`/`--plain`; `--color` forces | The four conditions of the CLI Guidelines (clig.dev); `NO_COLOR` per no-color.org |
| Unicode marks `✓ ● ! ✗ → · ←` with ASCII fallback (`--ascii` or non-UTF-8 stream) | Same meaning, no alignment breakage |
| Header (version, verb, project name, full path) on view commands only | Effect commands are one-liners often read by hooks; a header would be noise |
| Status column right-aligned in key/value blocks; a hint that does not fit the width moves under its line; findings never truncated; only header paths may be shortened | Adaptive to 80 columns; commands stay copyable |
| Piped output keeps the layout without colour; `--plain` is explicit and used by hooks | `ks doctor \| less` stays readable; scripts opt in to records |
| `--json` for status, sessions, doctor | Structured consumers (dashboards, tests) do not parse prose |
| Errors `✗ <verb>: <what> — <fix>`; refusals list the blockers and every way out | One shape; the fix is always the last, cyan thing on the line |
| Historical wording kept where hooks or docs depend on it (`session(s) active`, `version project X / installed Y`) | No behavioural change for the model |

## Consequences
- `ks project status`, `doctor`, `routing list|use`, `sessions`, `help`, refusals restyled; 8 new tests (plain/json/color/ascii equivalence). Screenshots in the KeelStone project under `design/ux/`.
- Skills and hooks that call `ks` should pass `--plain`.
