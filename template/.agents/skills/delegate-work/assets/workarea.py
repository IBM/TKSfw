#!/usr/bin/env python3
"""Create, list and prune subagent isolation spaces: git worktrees or agent work areas.

    workarea.py create <agent> <task-id> --session <token> [--worktree] [--instance N]
                                                            → prints the path; allocates the lowest free
                                                              instance (< [delegation] max_parallel_agents)
                                                              unless --instance reuses one
    workarea.py list [--json]
    workarea.py prune <agent> <task-id> [--session <token>] [--instance N] [--force]
    workarea.py prune --stale [--dry-run] [--force]         → work areas whose task is COMPLETED in tasks.md,
                                                              worktrees whose branch is merged
    workarea.py prune --session <token> [--dry-run] [--force] → everything this session created
    workarea.py status --json                               → used by the Stop hook (counts + stale list)

Key (1.4.0): <session-token>.<task-id>.<instance> — the session token is minted by the SessionStart hook
and shown in context; the instance number separates parallel copies of the same agent on the same task.
--session may be omitted only when exactly one session is active on the project.

Layout (project root = nearest ancestor with AGENTS.md or .agents/workarea, or $TKSFW_PROJECT_ROOT):
    .agents/workarea/<agent>/<session>.<task-id>.<n>/          work area (fallback isolation; never watched)
    .agents/worktrees/<agent>--<session>.<task-id>.<n>/        git worktree, branch agent/<agent>/<session>.<task-id>.<n>
Pre-1.4.0 names (<task-id> only) are still listed and pruned. Standard library only; exit 0 / 1.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json
import shutil
import subprocess

NAME_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")
TASK_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")          # no dots: '.' separates the key parts
TOKEN_RE = re.compile(r"^[0-9A-Za-z]{8}$")
KEY_RE = re.compile(r"^(?:([0-9A-Za-z]{8})\.)?([A-Za-z0-9_-]+)(?:\.(\d+))?$")   # session?.task.instance?


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


def max_parallel():
    """[delegation] max_parallel_agents from .agents/models.toml (default 4)."""
    try:
        import tomllib
        with open(os.path.join(ROOT, ".agents", "models.toml"), "rb") as fh:
            v = (tomllib.load(fh).get("delegation") or {}).get("max_parallel_agents", 4)
        return int(v) if int(v) > 0 else 4
    except Exception:
        return 4


def active_sessions(within=1800):
    """Session records with a recent heartbeat (.hook-state/sessions/<token>.json)."""
    import time
    d = os.path.join(WORKAREA, ".hook-state", "sessions")
    out = []
    try:
        for f in os.listdir(d):
            if f.endswith(".json"):
                try:
                    rec = json.load(open(os.path.join(d, f)))
                except Exception:
                    continue
                if time.time() - float(rec.get("last_seen", 0)) <= within:
                    out.append(rec)
    except FileNotFoundError:
        pass
    return out


def resolve_session(tok):
    if tok:
        if not TOKEN_RE.match(tok):
            sys.exit(f"session token {tok!r} must be base62, 8 chars (shown at session start)")
        return tok
    act = active_sessions()
    if len(act) == 1:
        return act[0]["token"]
    if not act:
        sys.exit("--session <token> required (no active session record found; the token is shown at session start)")
    sys.exit("--session <token> required: " + str(len(act)) + " sessions are active on this project ("
             + ", ".join(a["token"] for a in act) + ")")


def split_key(name):
    """'<session>.<task>.<n>' | '<task>' → (session, task, instance) with '' / None when absent."""
    m = KEY_RE.match(name)
    if not m:
        return None
    sess, task, inst = m.groups()
    return sess or "", task, (int(inst) if inst is not None else None)


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
            for name in sorted(os.listdir(ad)):
                td = os.path.join(ad, name)
                key = split_key(name)
                if os.path.isdir(td) and key:
                    sess, task, inst = key
                    items.append({"kind": "workarea", "agent": agent, "task": task, "session": sess, "instance": inst,
                                  "key": name, "path": td, "stale": task in done, "why": "task COMPLETED" if task in done else ""})
    if os.path.isdir(WORKTREES):
        for name in sorted(os.listdir(WORKTREES)):
            wd = os.path.join(WORKTREES, name)
            if not os.path.isdir(wd) or "--" not in name:
                continue
            agent, key = name.split("--", 1)
            parts = split_key(key)
            if not parts:
                continue
            sess, task, inst = parts
            branch = f"agent/{agent}/{key}"
            merged = branch_merged(branch) if git_available() else False
            items.append({"kind": "worktree", "agent": agent, "task": task, "session": sess, "instance": inst, "key": key,
                          "path": wd, "branch": branch,
                          "stale": merged or task in done, "why": "branch merged" if merged else ("task COMPLETED" if task in done else "")})
    return items


# ----------------------------------------------------------------------------- commands
def allocate(agent, task, sess, inst, worktree):
    """Lowest free instance under <agent>/<sess>.<task>.* (atomic: mkdir / worktree add fails if taken)."""
    cap = max_parallel()
    if inst is not None:
        if inst < 0 or inst >= cap:
            sys.exit(f"instance {inst} outside 0..{cap - 1} ([delegation] max_parallel_agents = {cap})")
        return inst
    base_dir = WORKTREES if worktree else os.path.join(WORKAREA, agent)
    prefix = (f"{agent}--" if worktree else "") + f"{sess}.{task}."
    used = set()
    try:
        for n in os.listdir(base_dir):
            if n.startswith(prefix) and n[len(prefix):].isdigit():
                used.add(int(n[len(prefix):]))
    except FileNotFoundError:
        pass
    for i in range(cap):
        if i not in used:
            return i
    sys.exit(f"all {cap} instances of {agent} on {sess}.{task} exist — prune one or raise [delegation] max_parallel_agents")


def cmd_create(agent, task, worktree, sess, inst):
    if not NAME_RE.match(agent):
        sys.exit(f"agent name {agent!r} must be lowercase letters and hyphens (<family>-<role>)")
    if not TASK_RE.match(task):
        sys.exit(f"task id {task!r}: letters, digits, _ - only (no dots)")
    sess = resolve_session(sess)
    inst = allocate(agent, task, sess, inst, worktree)
    key = f"{sess}.{task}.{inst}"
    if worktree:
        if not git_available():
            sys.exit("git worktree requested but the project is not a git work tree — omit --worktree to use a work area")
        wd = os.path.join(WORKTREES, f"{agent}--{key}")
        branch = f"agent/{agent}/{key}"
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
    wd = os.path.join(WORKAREA, agent, key)
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


def opt(args, name):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return None


def cmd_prune(args):
    force, dry, stale = "--force" in args, "--dry-run" in args, "--stale" in args
    sess, inst = opt(args, "--session"), opt(args, "--instance")
    skip = {sess, inst}
    pos = [a for a in args if not a.startswith("--") and a not in skip]
    items = inventory()
    if stale:
        targets = [i for i in items if i["stale"]]
        if not targets:
            print("nothing stale")
            return 0
    elif sess and not pos:
        targets = [i for i in items if i["session"] == sess]
        if not targets:
            print(f"nothing for session {sess}")
            return 0
    else:
        if len(pos) != 2:
            sys.exit("usage: prune <agent> <task-id> [--session T] [--instance N] [--force] | prune --stale | prune --session T")
        targets = [i for i in items if i["agent"] == pos[0] and i["task"] == pos[1]
                   and (not sess or i["session"] == sess) and (inst is None or i["instance"] == int(inst))]
        if not targets:
            sys.exit(f"no worktree or work area for {pos[0]} / {pos[1]}" + (f" / session {sess}" if sess else ""))
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
        print(f"{i['kind']:9} {i['agent']:<24} {i['key']:<28} {'STALE (' + i['why'] + ')' if i['stale'] else 'active':<28} {os.path.relpath(i['path'], ROOT)}")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    cmd = a[0]
    if cmd == "create":
        sess, inst = opt(a, "--session"), opt(a, "--instance")
        pos = [x for x in a[1:] if not x.startswith("--") and x not in {sess, inst}]
        if len(pos) != 2:
            sys.exit("usage: create <agent> <task-id> --session <token> [--worktree] [--instance N]")
        cmd_create(pos[0], pos[1], "--worktree" in a, sess, int(inst) if inst is not None else None)
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
