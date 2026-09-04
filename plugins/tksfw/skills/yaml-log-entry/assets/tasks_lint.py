#!/usr/bin/env python3
"""Advisory linter for the Activity Plan `tasks.md` (PWF gap R2).

Single-FILE checks only — grammar, status/checkbox agreement, duplicate IDs, and evidence-of-closing
PRESENCE at LEAF granularity. It does NOT resolve the `[ev:<EventID>]` foreign key to `events.yaml`;
that cross-file resolution is `cross_check.py`'s job (R1). This split keeps the linter a fast,
single-file check.

ADVISORY by design: `tasks.md` is edited in flux during planning, so this is meant to run in the
`verify-integrity` sweep / surface a count in STATE.md — NOT as a blocking PostToolUse gate. Exit
code is 0 (clean) / 1 (issues) so a caller MAY gate on it, but the intended use is reporting.

Usage: python3 tasks_lint.py [<tasks.md>]   (defaults to .claude/workarea/tasks.md)
Std lib only.
"""
import sys, os
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tasks_parse import parse_tasks   # shared single parser

DEFAULT_TASKS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "workarea", "tasks.md"))


def lint(text):
    """Return a list of advisory issue strings (empty = clean)."""
    tasks, _ = parse_tasks(text)
    issues, seen = [], {}
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
            issues.append(f"line {ln}: completed leaf task {t['id']} has no closing [ev:<EventID>] "
                          "(evidence-of-closing)")
        if t["ev"] and not completed:
            issues.append(f"line {ln}: [ev:{t['ev']}] on non-completed task {t['id']} "
                          "(closing evidence belongs only on COMPLETED tasks)")
    return issues


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DEFAULT_TASKS
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"tasks_lint: cannot read {path}: {e}")
        sys.exit(1)
    issues = lint(text)
    if not issues:
        print(f"tasks_lint: OK — {os.path.basename(path)} clean")
        sys.exit(0)
    print(f"tasks_lint: {len(issues)} advisory issue(s) in {os.path.basename(path)}:")
    for x in issues:
        print("  -", x)
    sys.exit(1)


if __name__ == "__main__":
    main()
