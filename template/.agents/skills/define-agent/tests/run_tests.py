#!/usr/bin/env python3
"""define-agent test suite: validate_agent.py against the fixtures (stdlib only)."""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
V = os.path.join(HERE, "..", "assets", "validate_agent.py")
FX = os.path.join(HERE, "fixtures")
MODELS = os.path.join(HERE, "..", "..", "..", "models.toml")
CASES = [  # (fixture, expected exit, substring expected in output)
    ("good/sources-researcher.toml", 0, "ok"),
    ("bad/atlas.toml", 2, "not in the vocabulary"),
    ("bad/src-fch.toml", 2, "role `fch`"),
    ("bad/main.toml", 2, "reserved"),
    ("bad/desc_prefix.toml", 2, "description"),
    ("bad/too-long-agent-name-reviewer.toml", 2, "tokens"),
    ("bad/mismatch.toml", 2, "filename"),
    ("bad/explorer.toml", 2, "built-in"),
    ("warn/report-builder.toml", 0, "warning"),
]
fails = 0
for fx, code, needle in CASES:
    r = subprocess.run([sys.executable, V, os.path.join(FX, fx), "--models", MODELS], capture_output=True, text=True)
    ok = r.returncode == code and needle in (r.stdout + r.stderr)
    print(f"[{'PASS' if ok else 'FAIL'}] {fx}  (exit {r.returncode}, expected {code})")
    if not ok:
        fails += 1
        print(r.stdout + r.stderr)
# warn fixture: model line is a warning in inline mode, an error in strip mode
import tempfile
with tempfile.TemporaryDirectory() as td:
    m = open(MODELS, encoding="utf-8").read().replace('codex_agent_files = "inline"', 'codex_agent_files = "strip"')
    mp = os.path.join(td, "models.toml"); open(mp, "w").write(m)
    r = subprocess.run([sys.executable, V, os.path.join(FX, "warn", "report-builder.toml"), "--models", mp], capture_output=True, text=True)
    ok = r.returncode == 2 and "must not be hand-written" in r.stdout
    print(f"[{'PASS' if ok else 'FAIL'}] strip mode: hand-written model is an error")
    fails += 0 if ok else 1
print(f"\n{len(CASES) + 1 - fails}/{len(CASES) + 1} cases passed")
sys.exit(1 if fails else 0)
