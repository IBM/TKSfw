#!/usr/bin/env python3
"""delegate-work skill tests: workarea.py create/list/prune with work areas and git worktrees."""
import os, sys, json, shutil, subprocess, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "assets", "workarea.py")
PY = sys.executable
fails = 0

def check(name, cond, detail=""):
    global fails
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  — {detail}" if detail and not cond else ""))
    fails += 0 if cond else 1

def run(args, cwd):
    return subprocess.run([PY, TOOL, *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, "TKSFW_PROJECT_ROOT": cwd})

tmp = tempfile.mkdtemp(prefix="tksfw-dw-")
try:
    os.makedirs(os.path.join(tmp, ".agents", "workarea"))
    open(os.path.join(tmp, "AGENTS.md"), "w").write("x\n")
    open(os.path.join(tmp, ".agents", "workarea", "tasks.md"), "w").write(
        "# plan\n- [x] T001 done - main : COMPLETED 2026-09-06 10:00:00 [ev:abc12345]\n- [ ] T002 open - main : OPEN 2026-09-06 10:00:00\n")
    r = run(["create", "x-builder", "T002"], tmp)
    check("work area created", r.returncode == 0 and os.path.isdir(os.path.join(tmp, ".agents", "workarea", "x-builder", "T002")), r.stderr)
    r = run(["create", "Bad_Name", "T002"], tmp)
    check("bad agent name refused", r.returncode != 0)
    r = run(["create", "x-builder", "T002", "--worktree"], tmp)
    check("worktree refused outside git", r.returncode != 0 and "not a git" in r.stderr)
    run(["create", "y-writer", "T001"], tmp)
    items = json.loads(run(["list", "--json"], tmp).stdout)
    check("list marks COMPLETED task stale", any(i["agent"] == "y-writer" and i["stale"] for i in items)
          and any(i["agent"] == "x-builder" and not i["stale"] for i in items))
    r = run(["prune", "--stale"], tmp)
    check("prune --stale removes only the stale work area", r.returncode == 0
          and not os.path.exists(os.path.join(tmp, ".agents", "workarea", "y-writer"))
          and os.path.isdir(os.path.join(tmp, ".agents", "workarea", "x-builder", "T002")), r.stdout + r.stderr)
    # git worktrees
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp, capture_output=True, text=True)
    g("init", "-q"); g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    r = run(["create", "z-reviewer", "T002", "--worktree"], tmp)
    wt = os.path.join(tmp, ".agents", "worktrees", "z-reviewer--T002")
    check("worktree created on agent/<agent>/<task>", r.returncode == 0 and os.path.isdir(wt)
          and ".agents/worktrees/" in open(os.path.join(tmp, ".gitignore")).read(), r.stderr)
    open(os.path.join(wt, "f.txt"), "w").write("w\n")
    subprocess.run(["git", "add", "f.txt"], cwd=wt); subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "w"], cwd=wt)
    r = run(["prune", "z-reviewer", "T002"], tmp)
    check("unmerged worktree refused without --force", r.returncode != 0 and os.path.isdir(wt), r.stdout)
    g("merge", "-q", "agent/z-reviewer/T002")
    items = json.loads(run(["list", "--json"], tmp).stdout)
    check("merged worktree reported stale", any(i["kind"] == "worktree" and i["stale"] for i in items))
    r = run(["prune", "--stale"], tmp)
    check("merged worktree pruned and branch deleted", r.returncode == 0 and not os.path.exists(wt)
          and g("rev-parse", "--verify", "--quiet", "agent/z-reviewer/T002").returncode != 0, r.stdout + r.stderr)
    st = json.loads(run(["status", "--json"], tmp).stdout)
    check("status --json", st["total"] == 1 and st["stale"] == [])
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
