#!/usr/bin/env python3
"""Linter for the Activity Plan `tasks.md` (grammar reference: ../references/tasks.md).

Single-FILE checks only — grammar, status/checkbox agreement, duplicate IDs, and evidence-of-closing
PRESENCE at LEAF granularity. It does NOT resolve the `[ev:<EventID>]` foreign key to `events.yaml`;
that cross-file resolution is `cross_check.py`'s job. Two severities (since 1.3.0):

  ERROR  malformed line (grammar / unknown status / bad timestamp), duplicate TaskID, checkbox that
         disagrees with the status  → deterministic, syntactic; the PostToolUse hook BLOCKS on these
         (exit 2) so a plan write is either well-formed or rejected with the expected grammar.
  WARN   completed leaf without [ev:…], [ev:…] on a non-completed task → the SHOULD-rules; the hook
         only reports them (systemMessage); STATE.md and verify-integrity keep counting them.

Exit codes: 0 clean · 1 warnings only · 2 errors.   `--json` prints {"errors": [...], "warnings": [...]}.
Usage: python3 tasks_lint.py [<tasks.md>] [--json]   (defaults to .agents/workarea/tasks.md)
Std lib only.
"""
import json
import sys, os
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tasks_parse import parse_tasks   # shared single parser

DEFAULT_TASKS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "workarea", "tasks.md"))


def lint_split(text):
    """Return (errors, warnings) — lists of issue strings."""
    tasks, _ = parse_tasks(text)
    errors, warnings, seen = [], [], {}
    issues = errors                                        # default sink; swapped per rule below
    for t in tasks:
        ln = t["lineno"]
        if not t["well_formed"]:
            issues.append(f"line {ln}: malformed task line — expected "
                          "'<TaskID> <Title> - <AgentName> : <STATUS> <YYYY-MM-DD hh:mm:ss>'")
            continue
        if t["id"] in seen:
            issues.append(f"line {ln}: duplicate TaskID {t['id']} (first seen at line {seen[t['id']]})")
        else:
            seen[t["id"]] = ln
        completed = t["status"] == "COMPLETED"
        if t["done_box"] != completed:
            box = "x" if t["done_box"] else " "
            issues.append(f"line {ln}: checkbox [{box}] disagrees with status {t['status']} ({t['id']})")
        if completed and t["is_leaf"] and not t["ev"]:
            warnings.append(f"line {ln}: completed leaf task {t['id']} has no closing [ev:<EventID>] "
                            "(evidence-of-closing)")
        if t["ev"] and not completed:
            warnings.append(f"line {ln}: [ev:{t['ev']}] on non-completed task {t['id']} "
                            "(closing evidence belongs only on COMPLETED tasks)")
    return errors, warnings


def lint(text):
    """All issues as one list (errors first) — kept for STATE.md's count and older callers."""
    e, w = lint_split(text)
    return e + w


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DEFAULT_TASKS
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"tasks_lint: cannot read {path}: {e}")
        sys.exit(1)
    errors, warnings = lint_split(text)
    if "--json" in sys.argv:
        print(json.dumps({"errors": errors, "warnings": warnings}))
        sys.exit(2 if errors else 1 if warnings else 0)
    if not errors and not warnings:
        print(f"tasks_lint: OK — {os.path.basename(path)} clean")
        sys.exit(0)
    if errors:
        print(f"tasks_lint: {len(errors)} ERROR(s) in {os.path.basename(path)} (grammar: ../references/tasks.md):")
        for x in errors:
            print("  -", x)
    if warnings:
        print(f"tasks_lint: {len(warnings)} warning(s) in {os.path.basename(path)}:")
        for x in warnings:
            print("  -", x)
    sys.exit(2 if errors else 1)


if __name__ == "__main__":
    main()
