#!/usr/bin/env python3
"""Create, list and prune subagent isolation spaces: git worktrees or agent work areas.

    workarea.py create <agent> <task-id> [--worktree]      → prints the path (idempotent)
    workarea.py list [--json]
    workarea.py prune <agent> <task-id> [--force]           → remove one (worktree: refuse if unmerged)
    workarea.py prune --stale [--dry-run] [--force]         → remove work areas whose task is COMPLETED in
                                                              tasks.md and worktrees whose branch is merged
    workarea.py status --json                               → used by the Stop hook (counts + stale list)

Layout (project root = nearest ancestor with AGENTS.md or .agents/workarea, or $TKSFW_PROJECT_ROOT):
    .agents/workarea/<agent>/<task-id>/          work area (fallback isolation; never watched, never a deliverable)
    .agents/worktrees/<agent>--<task-id>/        git worktree on branch agent/<agent>/<task-id>
Standard library only; exit 0 on success, 1 on refusal/error.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json
import shutil
import subprocess

NAME_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")
TASK_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def project_root():
    p = os.environ.get("TKSFW_PROJECT_ROOT")
    if p and os.path.isdir(p):
        return os.path.abspath(p)
    cur = os.path.abspath(os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "AGENTS.md")) or os.path.isdir(os.path.join(cur, ".agents", "workarea")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(os.getcwd())
        cur = parent


ROOT = project_root()
WORKAREA = os.path.join(ROOT, ".agents", "workarea")
WORKTREES = os.path.join(ROOT, ".agents", "worktrees")
TASKS_MD = os.path.join(WORKAREA, "tasks.md")
LEDGER_FILES = {"changes.yaml", "lessons.yaml", "handoffs.yaml", "events.yaml", "decisions.yaml",
                "deliverables.yaml", "tasks.md", "tasks-archive.md", "STATE.md", ".hook-state", ".keep"}


def git(*args, check=False):
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except Exception as e:
        return 1, "", str(e)
    if check and r.returncode:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.returncode, r.stdout, r.stderr


def git_available():
    rc, out, _ = git("rev-parse", "--is-inside-work-tree")
    return rc == 0 and out.strip() == "true"


def completed_tasks():
    """Set of task ids marked COMPLETED in tasks.md (shared parser when available)."""
    ids = set()
    if not os.path.isfile(TASKS_MD):
        return ids
    try:
        parser_dir = os.path.join(ROOT, ".agents", "skills", "yaml-log-entry", "assets")
        if not os.path.isdir(parser_dir):                        # plugin layout: sibling skill
            parser_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                      "yaml-log-entry", "assets")
        sys.path.insert(0, parser_dir)
        from tasks_parse import parse_tasks, is_completed
        tasks, _ = parse_tasks(open(TASKS_MD, encoding="utf-8").read())
        return {t["id"] for t in tasks if is_completed(t)}
    except Exception:
        for line in open(TASKS_MD, encoding="utf-8", errors="replace"):
            m = re.match(r"^\s*-\s*\[x\]\s+([A-Za-z0-9._-]+)", line)
            if m:
                ids.add(m.group(1))
        return ids


def branch_merged(branch):
    rc, out, _ = git("branch", "--merged", "HEAD", "--format=%(refname:short)")
    return rc == 0 and branch in {l.strip() for l in out.splitlines()}


# ----------------------------------------------------------------------------- inventory
def inventory():
    done = completed_tasks()
    items = []
    if os.path.isdir(WORKAREA):
        for agent in sorted(os.listdir(WORKAREA)):
            ad = os.path.join(WORKAREA, agent)
            if agent in LEDGER_FILES or agent.startswith(".") or not os.path.isdir(ad):
                continue
            for task in sorted(os.listdir(ad)):
                td = os.path.join(ad, task)
                if os.path.isdir(td):
                    items.append({"kind": "workarea", "agent": agent, "task": task, "path": td,
                                  "stale": task in done, "why": "task COMPLETED" if task in done else ""})
    if os.path.isdir(WORKTREES):
        for name in sorted(os.listdir(WORKTREES)):
            wd = os.path.join(WORKTREES, name)
            if not os.path.isdir(wd) or "--" not in name:
                continue
            agent, task = name.split("--", 1)
            branch = f"agent/{agent}/{task}"
            merged = branch_merged(branch) if git_available() else False
            items.append({"kind": "worktree", "agent": agent, "task": task, "path": wd, "branch": branch,
                          "stale": merged or task in done, "why": "branch merged" if merged else ("task COMPLETED" if task in done else "")})
    return items


# ----------------------------------------------------------------------------- commands
def cmd_create(agent, task, worktree):
    if not NAME_RE.match(agent):
        sys.exit(f"agent name {agent!r} must be lowercase letters and hyphens (<family>-<role>)")
    if not TASK_RE.match(task):
        sys.exit(f"task id {task!r}: letters, digits, . _ - only")
    if worktree:
        if not git_available():
            sys.exit("git worktree requested but the project is not a git work tree — omit --worktree to use a work area")
        wd = os.path.join(WORKTREES, f"{agent}--{task}")
        branch = f"agent/{agent}/{task}"
        if os.path.isdir(wd):
            print(wd)
            return
        os.makedirs(WORKTREES, exist_ok=True)
        rc, _o, _e = git("rev-parse", "--verify", "--quiet", branch)
        args = ["worktree", "add", wd] + ([branch] if rc == 0 else ["-b", branch])
        try:
            git(*args, check=True)
        except RuntimeError as e:
            sys.exit(f"git worktree add failed: {e}")
        ensure_ignored()
        print(wd)
        return
    wd = os.path.join(WORKAREA, agent, task)
    os.makedirs(wd, exist_ok=True)
    print(wd)


def ensure_ignored():
    """Worktrees must not be committed into the parent repo: add .agents/worktrees/ to .gitignore."""
    gi = os.path.join(ROOT, ".gitignore")
    line = ".agents/worktrees/"
    try:
        cur = open(gi, encoding="utf-8").read() if os.path.isfile(gi) else ""
        if line not in cur.splitlines():
            with open(gi, "a", encoding="utf-8") as fh:
                fh.write(("" if cur.endswith("\n") or not cur else "\n") + line + "\n")
    except Exception:
        pass


def remove_item(it, force, dry):
    if it["kind"] == "worktree":
        if not it["stale"] and not force:
            print(f"refused: {it['path']} — branch {it['branch']} not merged and task not COMPLETED (use --force)")
            return False
        if dry:
            print(f"would remove worktree {it['path']}")
            return True
        rc, _o, err = git("worktree", "remove", "--force", it["path"])
        if rc:
            print(f"git worktree remove failed: {err.strip()}")
            return False
        if it["stale"] and branch_merged(it["branch"]):
            git("branch", "-D", it["branch"])
        print(f"removed worktree {it['path']}")
        return True
    if dry:
        print(f"would remove work area {it['path']}")
        return True
    shutil.rmtree(it["path"], ignore_errors=True)
    parent = os.path.dirname(it["path"])
    try:
        if not os.listdir(parent):
            os.rmdir(parent)
    except Exception:
        pass
    print(f"removed work area {it['path']}")
    return True


def cmd_prune(args):
    force, dry, stale = "--force" in args, "--dry-run" in args, "--stale" in args
    pos = [a for a in args if not a.startswith("--")]
    items = inventory()
    if stale:
        targets = [i for i in items if i["stale"]]
        if not targets:
            print("nothing stale")
            return 0
    else:
        if len(pos) != 2:
            sys.exit("usage: prune <agent> <task-id> [--force] | prune --stale [--dry-run]")
        targets = [i for i in items if i["agent"] == pos[0] and i["task"] == pos[1]]
        if not targets:
            sys.exit(f"no worktree or work area for {pos[0]} / {pos[1]}")
    ok = all(remove_item(i, force, dry) for i in targets)
    if git_available() and not dry:
        git("worktree", "prune")
    return 0 if ok else 1


def cmd_list(as_json):
    items = inventory()
    if as_json:
        print(json.dumps(items, indent=2))
        return
    if not items:
        print("no worktrees or work areas")
        return
    for i in items:
        print(f"{i['kind']:9} {i['agent']:<24} {i['task']:<14} {'STALE (' + i['why'] + ')' if i['stale'] else 'active':<28} {os.path.relpath(i['path'], ROOT)}")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    cmd = a[0]
    if cmd == "create":
        pos = [x for x in a[1:] if not x.startswith("--")]
        if len(pos) != 2:
            sys.exit("usage: create <agent> <task-id> [--worktree]")
        cmd_create(pos[0], pos[1], "--worktree" in a)
    elif cmd == "list":
        cmd_list("--json" in a)
    elif cmd == "status":
        items = inventory()
        print(json.dumps({"total": len(items), "stale": [i for i in items if i["stale"]]}, indent=2))
    elif cmd == "prune":
        sys.exit(cmd_prune(a[1:]))
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main()
