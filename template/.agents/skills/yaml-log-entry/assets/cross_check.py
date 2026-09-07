#!/usr/bin/env python3
"""Cross-ledger referential integrity (PWF gap R1).

Per-file validation (validate_yaml_log.py, run by the PostToolUse hook) proves each entry is
well-formed; it does NOT prove the GRAPH is consistent. This checker resolves the foreign keys
ACROSS files and flags orphans / dangling references / unpaired handoffs:

  * events.yaml     — each `TaskID` resolves to a task in tasks.md or archive/tasks.md (legacy tasks-archive.md)
  Archives (`archive/<ledger>.yaml`) are read together with the live ledgers: an evidence link into an
  archived event stays valid.
  * handoffs.yaml   — each `EventID` resolves in events.yaml; each `TaskID` resolves to a task;
                      every `<stem>-BEGIN` has a matching `<stem>-END` (BEGIN-only = open = WARN;
                      END-only = ERROR)
  * decisions.yaml  — every `RelatedTo.{Tasks,Decisions,Changes,Lessons,Events}` id resolves to
                      the corresponding file
  * tasks.md        — each COMPLETED task's closing `[ev:<EventID>]` resolves to an events.yaml
                      entry whose `TaskID` matches back and whose EventType/Status is
                      terminal-positive (the evidence-of-closing FK, R2 ↔ R1)

TaskIDs are unioned across the live plan AND the archive (events may reference completed, archived
tasks). Evidence FKs are checked on the LIVE tasks.md only (the archive is frozen history).

Exit 1 on any ERROR (a genuine dangling FK); WARNs (e.g. an open handoff) do not fail. Runs as part
of the `verify-integrity` sweep — NOT a per-write PostToolUse gate (it is multi-file).

Usage: python3 cross_check.py [--workarea <dir>]   (default: the project's .claude/workarea)
Std lib only.
"""
import sys
import re, os
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_yaml_log import load_entries
from tasks_parse import parse_tasks

DEFAULT_WORKAREA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "workarea"))

# Event (EventType -> statuses) that legitimately CLOSE a task (terminal-positive).
CLOSING = {
    "TASK": {"COMPLETED"}, "REVIEW": {"PASS"}, "AUDIT": {"CONFORMANT"}, "APPROVAL": {"GO"},
    "HANDOFF": {"END"}, "CHANGE": {"COMPLETED"},
}


SHARD_RE = re.compile(r"^(changes|lessons|handoffs|events|decisions)\.([0-9A-Za-z]{8})\.yaml$")


def ledger_files(name, workarea, with_archive=True):
    """Legacy `<name>` + every session shard `<kind>.<token>.yaml` (+ archive)."""
    kind = name[:-5]
    paths = [os.path.join(workarea, name)]
    try:
        paths += [os.path.join(workarea, n) for n in sorted(os.listdir(workarea)) if SHARD_RE.match(n) and n.startswith(kind + ".")]
    except FileNotFoundError:
        pass
    if with_archive:
        paths.append(os.path.join(workarea, "archive", name))
    return [p for p in paths if os.path.exists(p)]


def _load(name, workarea, with_archive=True):
    """Entries of a ledger kind across legacy file, session shards and (by default) the archive —
    FKs may point anywhere in that set."""
    out = []
    for p in ledger_files(name, workarea, with_archive):
        try:
            entries, _ = load_entries(p)
            out.extend(entries)
        except Exception:
            pass
    return out


def _parse_tasks_file(name, workarea):
    p = os.path.join(workarea, name)
    if not os.path.exists(p):
        return []
    try:
        tasks, _ = parse_tasks(open(p, encoding="utf-8").read())
        return tasks
    except Exception:
        return []


def check(workarea=DEFAULT_WORKAREA):
    """Return (errors, warns)."""
    errors, warns = [], []

    task_ids = {t["id"] for fn in ("tasks.md", "tasks-archive.md", os.path.join("archive", "tasks.md"))
                for t in _parse_tasks_file(fn, workarea)}

    events = _load("events.yaml", workarea)
    ev_by = {eid: f for eid, f in events if isinstance(f, dict)}
    ev_ids = set(ev_by)
    dec = _load("decisions.yaml", workarea)
    dec_ids = {i for i, _ in dec}
    chg_ids = {i for i, _ in _load("changes.yaml", workarea)}
    les_ids = {i for i, _ in _load("lessons.yaml", workarea)}

    # 1) events.TaskID -> tasks
    for eid, f in events:
        if not isinstance(f, dict):
            continue
        tid = f.get("TaskID")
        if tid and tid != "N/A" and tid not in task_ids:
            errors.append(f"events.yaml/{eid}: TaskID '{tid}' not found in tasks.md or archive")

    # 2) handoffs: EventID/TaskID resolve; BEGIN/END pairing
    stems = {}
    for hid, f in _load("handoffs.yaml", workarea):
        stem, _, half = hid.rpartition("-")
        stems.setdefault(stem or hid, set()).add(half)
        if not isinstance(f, dict):
            continue
        eid = f.get("EventID")
        if eid and eid != "N/A" and eid not in ev_ids:
            errors.append(f"handoffs.yaml/{hid}: EventID '{eid}' not in events.yaml")
        tid = f.get("TaskID")
        if tid and tid != "N/A" and tid not in task_ids:
            errors.append(f"handoffs.yaml/{hid}: TaskID '{tid}' not in tasks.md or archive")
    for stem, halves in stems.items():
        if "BEGIN" in halves and "END" not in halves:
            warns.append(f"handoffs.yaml: '{stem}' has BEGIN but no END (open/incomplete handoff)")
        if "END" in halves and "BEGIN" not in halves:
            errors.append(f"handoffs.yaml: '{stem}' has END but no BEGIN")

    # 2b) events.DecisionID -> decisions (status transitions of partitioned, append-only decisions)
    for eid, f in events:
        if isinstance(f, dict) and f.get("DecisionID") and f["DecisionID"] not in dec_ids:
            errors.append(f"events/{eid}: DecisionID '{f['DecisionID']}' not found in decisions")

    # 3) decisions.RelatedTo.* -> respective files
    rel_target = {"Tasks": task_ids, "Decisions": dec_ids, "Changes": chg_ids,
                  "Lessons": les_ids, "Events": ev_ids}
    for did, f in dec:
        rel = f.get("RelatedTo") if isinstance(f, dict) else None
        if not isinstance(rel, dict):
            continue
        for sub, ids in rel.items():
            target = rel_target.get(sub)
            if target is None or not isinstance(ids, list):
                continue
            for rid in ids:
                if isinstance(rid, str) and rid not in target:
                    errors.append(f"decisions.yaml/{did}: RelatedTo.{sub} '{rid}' not found in {sub.lower()}")

    # 4) tasks.md evidence-of-closing FK (live plan only)
    for t in _parse_tasks_file("tasks.md", workarea):
        if not t["well_formed"] or t["status"] != "COMPLETED" or not t["ev"]:
            continue
        eid = t["ev"]
        if eid not in ev_ids:
            errors.append(f"tasks.md L{t['lineno']}: [ev:{eid}] for {t['id']} not in events.yaml")
            continue
        f = ev_by[eid]
        etid, etype, est = f.get("TaskID"), f.get("EventType"), f.get("Status")
        if etid and etid != t["id"]:
            errors.append(f"tasks.md L{t['lineno']}: [ev:{eid}] event TaskID '{etid}' != task '{t['id']}'")
        if est not in CLOSING.get(etype, set()):
            errors.append(f"tasks.md L{t['lineno']}: [ev:{eid}] event {etype}/{est} is not terminal-positive")

    return errors, warns


def main():
    workarea = DEFAULT_WORKAREA
    if "--workarea" in sys.argv:
        i = sys.argv.index("--workarea")
        if i + 1 < len(sys.argv):
            workarea = sys.argv[i + 1]
    errors, warns = check(workarea)
    for w in warns:
        print("WARN:", w)
    if errors:
        print(f"\nFAIL — {len(errors)} cross-ledger integrity error(s):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"PASS — cross-ledger integrity OK ({len(warns)} warning(s))")
    sys.exit(0)


if __name__ == "__main__":
    main()
