#!/usr/bin/env python3
"""Regression tests for the log/plan tooling (PWF gap R3).

Runs the three checkers against committed fixtures and asserts EXIT CODES — the tooling is the
guardrail for every ledger, so a silent regression here would disable enforcement everywhere.
Covers: validate_yaml_log.py (good + known-bad per representative kind), tasks_lint.py (clean +
issues), and cross_check.py (consistent graph + dangling FKs).

Run:  python3 .claude/skills/yaml-log-entry/tests/run_tests.py
Exit 0 = all cases matched expected exit codes; 1 = at least one mismatch. Std lib only; leaves no
bytecode (PYTHONDONTWRITEBYTECODE forced for subprocesses).
"""
import sys, os, subprocess
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.normpath(os.path.join(HERE, "..", "assets"))
FIX = os.path.join(HERE, "fixtures")
VALIDATE = os.path.join(ASSETS, "validate_yaml_log.py")
LINT = os.path.join(ASSETS, "tasks_lint.py")
CROSS = os.path.join(ASSETS, "cross_check.py")
PY = sys.executable or "python3"


def f(name):
    return os.path.join(FIX, name)


# (description, argv after the python interpreter, expected exit code)
CASES = [
    ("validator: good changes",          [VALIDATE, f("good_changes.yaml"), "changes"], 0),
    ("validator: bad changes Layer enum", [VALIDATE, f("bad_changes_layer.yaml"), "changes"], 1),
    ("validator: good decisions",        [VALIDATE, f("good_decisions.yaml"), "decisions"], 0),
    ("validator: bad decisions enum",    [VALIDATE, f("bad_decisions_enum.yaml"), "decisions"], 1),
    ("validator: bad lessons title>80",  [VALIDATE, f("bad_lessons_title.yaml"), "lessons"], 1),
    ("validator: good deliverables",     [VALIDATE, f("good_deliverables.yaml"), "deliverables"], 0),
    ("validator: bad deliverables path", [VALIDATE, f("bad_deliverables_path.yaml"), "deliverables"], 1),
    ("validator: good events",           [VALIDATE, f("good_events.yaml"), "events"], 0),
    ("validator: bad events pairing",    [VALIDATE, f("bad_events_status.yaml"), "events"], 1),
    ("validator: bad REVIEW status",     [VALIDATE, f("bad_review_status.yaml"), "events"], 1),
    ("validator: bad TEST status",       [VALIDATE, f("bad_test_status.yaml"), "events"], 1),
    ("tasks_lint: clean plan",           [LINT, f("good_tasks.md")], 0),
    ("tasks_lint: plan with errors → 2", [LINT, f("bad_tasks.md")], 2),
    ("tasks_lint: warnings only → 1",    [LINT, f("warn_tasks.md")], 1),
    ("cross_check: consistent graph",    [CROSS, "--workarea", os.path.join(FIX, "cross_good")], 0),
    ("cross_check: dangling FKs",        [CROSS, "--workarea", os.path.join(FIX, "cross_bad")], 1),
]


def main():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    passed = failed = 0
    for desc, argv, expected in CASES:
        r = subprocess.run([PY] + argv, capture_output=True, text=True, env=env)
        ok = r.returncode == expected
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}  (exit {r.returncode}, expected {expected})")
        if ok:
            passed += 1
        else:
            failed += 1
            # show a little context on failure
            out = (r.stdout + r.stderr).strip().splitlines()
            for line in out[:4]:
                print("        |", line)
    print(f"\n{passed}/{passed + failed} cases passed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
