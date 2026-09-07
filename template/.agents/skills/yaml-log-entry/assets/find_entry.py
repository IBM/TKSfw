#!/usr/bin/env python3
"""Find a ledger entry or task by ID across the live ledgers, the archives and the plan; show what
references it.

    find_entry.py <ID>            entry (YAML block) or task line, with file:line
    find_entry.py <ID> --refs     + every entry/task that references it (TaskID, EventID, RelatedTo, [ev:…])
    find_entry.py --prefix <chars>  partial IDs
    find_entry.py <ID> --json

Handoff stems match both halves (`7Kd2Rf9Q` → `7Kd2Rf9Q-BEGIN` and `-END`). Searched files:
`.agents/workarea/{changes,lessons,handoffs,events,decisions,deliverables}.yaml`, `archive/*.yaml`,
`tasks.md`, `archive/tasks.md` (and legacy `tasks-archive.md`). Std lib only; exit 0 found / 1 not found.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_yaml_log import load_entries   # noqa: E402

ENTRY_START = re.compile(r'^-\s+["\']?([0-9A-Za-z]{1,32}(?:-(?:BEGIN|END))?)["\']?:\s*$')
TASK_LINE = re.compile(r"^\s*-\s*\[[ xX]\]\s+([A-Za-z0-9_-]+)\s")
EV_RE = re.compile(r"\[ev:([0-9A-Za-z]{8})\]")
LEDGERS = ("changes.yaml", "lessons.yaml", "handoffs.yaml", "events.yaml", "decisions.yaml", "deliverables.yaml")


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


def files(wa):
    out = []
    for n in LEDGERS:
        for p in (os.path.join(wa, n), os.path.join(wa, "archive", n)):
            if os.path.isfile(p):
                out.append(("ledger", p))
    for p in (os.path.join(wa, "tasks.md"), os.path.join(wa, "archive", "tasks.md"), os.path.join(wa, "tasks-archive.md")):
        if os.path.isfile(p):
            out.append(("plan", p))
    return out


def blocks(path):
    """[(id, lineno, raw)] top-level entries of a ledger file."""
    out, cur = [], None
    for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        m = ENTRY_START.match(line)
        if m:
            if cur:
                out.append(tuple(cur))
            cur = [m.group(1), n, line]
        elif cur:
            cur[2] += line
    if cur:
        out.append(tuple(cur))
    return out


def matches(eid, wanted, prefix):
    if prefix:
        return eid.startswith(wanted)
    return eid == wanted or eid.split("-")[0] == wanted


def find(wanted, wa, prefix=False):
    hits = []
    for kind, p in files(wa):
        rel = os.path.relpath(p, wa)
        if kind == "ledger":
            for eid, ln, raw in blocks(p):
                if matches(eid, wanted, prefix):
                    hits.append({"id": eid, "file": rel, "line": ln, "text": raw.rstrip("\n"), "kind": "entry"})
        else:
            for ln, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                m = TASK_LINE.match(line)
                if m and matches(m.group(1), wanted, prefix):
                    hits.append({"id": m.group(1), "file": rel, "line": ln, "text": line.rstrip("\n"), "kind": "task"})
    return hits


def _walk_ids(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _walk_ids(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk_ids(x)
    elif v is not None:
        yield str(v)


def refs(wanted, wa):
    """Entries/tasks referencing `wanted` (or its handoff stem)."""
    stem = wanted.split("-")[0]
    out = []
    for kind, p in files(wa):
        rel = os.path.relpath(p, wa)
        if kind == "ledger":
            try:
                entries, _ = load_entries(p)
            except Exception:
                continue
            for eid, f in entries:
                if not isinstance(f, dict) or eid == wanted or eid.split("-")[0] == stem:
                    continue
                where = []
                for key in ("TaskID", "EventID", "RelatedTo", "Inputs", "Outputs", "Scope"):
                    vals = set(_walk_ids(f.get(key)))
                    if wanted in vals or stem in vals or any(stem in str(x) for x in vals if key in ("Inputs", "Outputs", "Scope")):
                        where.append(key)
                if where:
                    out.append({"id": eid, "file": rel, "via": where, "title": str(f.get("Title", ""))[:80]})
        else:
            for ln, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                if wanted in line or stem in line:
                    m = TASK_LINE.match(line)
                    if m and m.group(1) != wanted:
                        via = ["[ev:]"] if EV_RE.search(line) and stem in (EV_RE.search(line).group(1)) else ["text"]
                        out.append({"id": m.group(1), "file": rel, "line": ln, "via": via, "title": line.strip()[:80]})
    return out


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    prefix = "--prefix" in a
    as_json = "--json" in a
    want_refs = "--refs" in a
    pos = [x for x in a if not x.startswith("--")]
    if not pos:
        sys.exit("usage: find_entry.py <ID> [--refs] [--json] | --prefix <chars>")
    wanted = pos[0]
    wa = workarea()
    hits = find(wanted, wa, prefix)
    rr = refs(wanted, wa) if want_refs and not prefix else []
    if as_json:
        print(json.dumps({"query": wanted, "hits": hits, "refs": rr}, indent=2))
        sys.exit(0 if hits else 1)
    if not hits:
        print(f"{wanted}: not found in {os.path.relpath(wa)}")
        sys.exit(1)
    for h in hits:
        print(f"== {h['file']}:{h['line']}  ({h['kind']})")
        print(h["text"])
    if want_refs:
        print(f"\n-- referenced by ({len(rr)}):" if rr else "\n-- referenced by: none")
        for r in rr:
            loc = f"{r['file']}" + (f":{r['line']}" if "line" in r else "")
            print(f"  {r['id']:<16} {loc:<32} via {', '.join(r['via']):<18} {r['title']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
