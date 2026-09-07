#!/usr/bin/env python3
"""Move closed history out of the live ledgers into the cumulative per-type archives.

    archive_ledger.py plan   [--dry-run]                      tasks.md → archive/tasks.md
    archive_ledger.py <ledger|all> --before YYYY-MM-DD [--dry-run]
                                                              changes|lessons|events|handoffs|decisions
                                                              → archive/<ledger>.yaml

Layout: `.agents/workarea/archive/` holds ONE cumulative, append-only archive per type with the same
schema as the live file. Entries move verbatim (owner fields preserved). The PostToolUse hook accepts an
ID leaving a live ledger only when it is already present in archive/<same ledger> — so the protocol is
append-to-archive first, then remove from the live file (this script does exactly that, atomically per
file, and validates the archive before touching the live ledger). Legacy `tasks-archive.md` is migrated
into `archive/tasks.md` by `plan` on first run.

Eligibility — only closed history moves, so STATE.md's open-items view stays truthful:
  plan       plan blocks (heading + tasks) fully COMPLETED and followed by a newer block
  events     Status not OPEN, Timestamp < before
  handoffs   BEGIN with a matching END, both Timestamps < before (moved as a pair)
  decisions  Status in {SUPERSEDED, DEPRECATED} (ACCEPTED decisions are in force — they stay), LastUpdate < before
  changes, lessons   Timestamp < before
Std lib only. Exit 0 ok, 1 nothing to do / refused, 2 error.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_yaml_log import load_entries, validate, infer_kind   # noqa: E402
from tasks_parse import parse_tasks, is_open                       # noqa: E402

ENTRY_START = re.compile(r'^-\s+["\']?([0-9A-Za-z]{8}(?:-(?:BEGIN|END))?)["\']?:\s*$')
DATE_FIELD = {"changes": "Timestamp", "lessons": "Timestamp", "events": "Timestamp",
              "handoffs": "Timestamp", "decisions": "LastUpdate"}


def workarea():
    p = os.environ.get("TKSFW_PROJECT_ROOT")
    if p:
        return os.path.join(p, ".agents", "workarea")
    cur = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(cur, ".agents", "workarea")):
            return os.path.join(cur, ".agents", "workarea")
        parent = os.path.dirname(cur)
        if parent == cur:
            sys.exit("no .agents/workarea found upward from cwd (set TKSFW_PROJECT_ROOT)")
        cur = parent


# ----------------------------------------------------------------------------- raw blocks
def split_blocks(text):
    """[(id, raw_text)] for top-level `- <ID>:` entries, plus the preamble (comments/header) as text."""
    lines = text.splitlines(keepends=True)
    blocks, pre, cur_id, cur = [], [], None, []
    for line in lines:
        m = ENTRY_START.match(line)
        if m:
            if cur_id is not None:
                blocks.append((cur_id, "".join(cur)))
            cur_id, cur = m.group(1), [line]
        elif cur_id is None:
            pre.append(line)
        else:
            cur.append(line)
    if cur_id is not None:
        blocks.append((cur_id, "".join(cur)))
    return "".join(pre), blocks


def atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- ledgers
def eligible(kind, entries, before):
    """Set of IDs to move."""
    by = {eid: f for eid, f in entries if isinstance(f, dict)}
    fld = DATE_FIELD[kind]

    def old(eid):
        v = str(by.get(eid, {}).get(fld, ""))
        return bool(v) and v[:10] < before

    out = set()
    if kind == "handoffs":
        stems = {}
        for eid in by:
            stem, _, half = eid.partition("-")
            stems.setdefault(stem, set()).add(half)
        for stem, halves in stems.items():
            if {"BEGIN", "END"} <= halves and all(old(f"{stem}-{h}") for h in ("BEGIN", "END")):
                out.update({f"{stem}-BEGIN", f"{stem}-END"})
    elif kind == "events":
        out = {e for e in by if old(e) and str(by[e].get("Status", "OPEN")) != "OPEN"}
    elif kind == "decisions":
        out = {e for e in by if old(e) and str(by[e].get("Status")) in ("SUPERSEDED", "DEPRECATED")}
    else:
        out = {e for e in by if old(e)}
    return out


def archive_ledger(kind, before, dry, wa):
    live = os.path.join(wa, f"{kind}.yaml")
    arch = os.path.join(wa, "archive", f"{kind}.yaml")
    if not os.path.isfile(live):
        print(f"{kind}: no live ledger")
        return 1
    text = open(live, encoding="utf-8").read()
    entries, _ = load_entries(live)
    move = eligible(kind, entries, before)
    if not move:
        print(f"{kind}: nothing eligible before {before}")
        return 1
    pre, blocks = split_blocks(text)
    if {b[0] for b in blocks} != {e for e, _ in entries}:
        sys.exit(f"{kind}: raw block scan disagrees with the parser — file layout not canonical; refusing")
    moving = [b for b in blocks if b[0] in move]
    staying = [b for b in blocks if b[0] not in move]
    print(f"{kind}: {len(moving)} entr{'y' if len(moving) == 1 else 'ies'} → archive/{kind}.yaml"
          + (" (dry run)" if dry else ""))
    for eid, _ in moving:
        print("  -", eid)
    if dry:
        return 0
    os.makedirs(os.path.dirname(arch), exist_ok=True)
    existing = open(arch, encoding="utf-8").read() if os.path.isfile(arch) else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_arch = existing + "".join(b[1] for b in moving)
    atomic_write(arch, new_arch)
    problems, _ = validate(arch, kind)
    if problems:
        atomic_write(arch, existing)                       # roll back the archive append
        sys.exit(f"{kind}: archive would be invalid, nothing moved:\n  - " + "\n  - ".join(problems))
    atomic_write(live, pre + "".join(b[1] for b in staying))
    return 0


# ----------------------------------------------------------------------------- plan
def archive_plan(dry, wa):
    live = os.path.join(wa, "tasks.md")
    arch = os.path.join(wa, "archive", "tasks.md")
    legacy = os.path.join(wa, "tasks-archive.md")
    rc = 1
    if os.path.isfile(legacy):
        print(f"migrating tasks-archive.md → archive/tasks.md" + (" (dry run)" if dry else ""))
        if not dry:
            os.makedirs(os.path.dirname(arch), exist_ok=True)
            old = open(arch, encoding="utf-8").read() if os.path.isfile(arch) else ""
            atomic_write(arch, open(legacy, encoding="utf-8").read().rstrip("\n") + "\n" + old)
            os.remove(legacy)
        rc = 0
    if not os.path.isfile(live):
        print("plan: no tasks.md")
        return rc
    text = open(live, encoding="utf-8").read()
    tasks, _ = parse_tasks(text)
    lines = text.splitlines(keepends=True)
    # blocks = heading line .. next heading; a block is archivable when all its tasks are closed and a later block exists
    heads = [i for i, l in enumerate(lines) if re.match(r"^#{1,6}\s+\S", l)]
    if not heads:
        print("plan: no headed blocks (nothing to archive)")
        return rc
    spans = [(h, heads[k + 1] if k + 1 < len(heads) else len(lines)) for k, h in enumerate(heads)]
    by_line = {t["lineno"]: t for t in tasks}
    movable = []
    for k, (a, b) in enumerate(spans):
        ts = [by_line[n] for n in range(a + 1, b + 1) if n in by_line]
        if ts and k < len(spans) - 1 and all(not is_open(t) for t in ts):
            movable.append((a, b))
    if not movable:
        print("plan: no fully COMPLETED, superseded block")
        return rc
    print(f"plan: {len(movable)} block(s) → archive/tasks.md" + (" (dry run)" if dry else ""))
    for a, b in movable:
        print("  -", lines[a].strip())
    if dry:
        return 0
    os.makedirs(os.path.dirname(arch), exist_ok=True)
    old = open(arch, encoding="utf-8").read() if os.path.isfile(arch) else ""
    if old and not old.endswith("\n"):
        old += "\n"
    atomic_write(arch, old + "".join("".join(lines[a:b]) for a, b in movable))
    keep = set(range(len(lines))) - {i for a, b in movable for i in range(a, b)}
    atomic_write(live, "".join(lines[i] for i in sorted(keep)))
    return 0


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    dry = "--dry-run" in a
    wa = workarea()
    what = a[0]
    if what == "plan":
        sys.exit(archive_plan(dry, wa))
    if "--before" not in a:
        sys.exit("--before YYYY-MM-DD is required for ledgers")
    before = a[a.index("--before") + 1]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", before):
        sys.exit("--before must be YYYY-MM-DD")
    kinds = list(DATE_FIELD) if what == "all" else [what]
    for k in kinds:
        if k not in DATE_FIELD:
            sys.exit(f"unknown ledger {k!r} (one of {', '.join(DATE_FIELD)}, all, plan)")
    rcs = [archive_ledger(k, before, dry, wa) for k in kinds]
    sys.exit(0 if 0 in rcs else 1)


if __name__ == "__main__":
    main()
