#!/usr/bin/env python3
"""Generate `.agents/workarea/STATE.md` — a compact, always-regenerated projection of the current
project state (PWF gap C2). It is a **read-first resume cursor, NOT a source of truth**: it copies
no rule content, it only projects the authoritative files so a resuming (or post-compaction) agent
can reconstitute state from one short read.

Wired as a `Stop` hook (see `.agents/hooks/hooks.json`, mirrored to `.codex/hooks.json` and
`.claude/settings.json`) so it refreshes at every turn-end from the files on disk. Also imported
by `inject_state.py` (SessionStart) so the snapshot is regenerated right before it is injected
after startup/resume/compaction. Runnable standalone: `python3 refresh_state.py [--out <path>]
[--print]`. Harness-neutral: reads no hook payload fields.

Sources (authoritative — this script projects, never restates, their content):
  * tasks.md               — the plan. TaskIDs are RANDOM base62 (NO lexicographic order): order
                             and dependency come from DOCUMENT order (top→bottom, nested). So
                             "Next action" is the first non-COMPLETED task read top-down — never a
                             sort by ID or by timestamp.
  * .agents/workarea/*.yaml — ledger counts, open decisions/issues, dangling handoffs.
  * deliverables.yaml      — which deliverables currently exist on disk.
  * .hook-state/journal.jsonl — edits detected by track_edits.py that still lack a changes.yaml
                             entry (so a resuming agent knows what is pending to log).

"Last activity" = the MAX recorded timestamp across ledger *data*: every `Timestamp`
(changes/lessons/handoffs/events) + every `LastUpdate` (decisions) + every per-task
`LastUpdateDate` in tasks.md. It is the last *recorded* work time (self-reported in the data),
deliberately NOT filesystem mtime — this workspace is a cloud-synced (Box) folder, so mtimes are
perturbed by sync and would misreport. It is a `max()` over VALUES, so document/ID order cannot
skew it. The deliverables registry has no timestamps by design and is excluded.

Fail-open: every section is computed defensively; on error it degrades to "unknown" and the hook
never blocks a turn. Standard library only.
"""
import sys, os, re, glob
sys.dont_write_bytecode = True  # never leave __pycache__ in the workspace
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hooklib as H  # noqa: E402  (shared paths + journal reader)
PROJECT_ROOT = H.PROJECT_ROOT
WORKAREA = H.WORKAREA
WORKAREA_REL = H.WORKAREA_REL
VALIDATOR_DIR = H.VALIDATOR_DIR
OUT_DEFAULT = H.STATE_MD

# The tasks.md parser is the SHARED one in yaml-log-entry/assets (single parsing path — see
# tasks_parse.py). Import lazily/defensively so a missing module degrades the Focus section rather
# than crashing the hook.
sys.path.insert(0, VALIDATOR_DIR)
try:
    from tasks_parse import parse_tasks, is_open, TS_RE
except Exception:                                    # pragma: no cover - fail-open
    parse_tasks = None
    is_open = None
    TS_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
try:
    from tasks_lint import lint as lint_tasks         # advisory tasks.md lint (R2) — surface a count
except Exception:                                    # pragma: no cover - fail-open
    lint_tasks = None


def load_ledger(name):
    """(id, fields) entries via the shared pyyaml-optional parser; [] on any problem."""
    return H.load_entries(os.path.join(WORKAREA, name))


def unlogged_edits():
    """Watched files changed by the agent (journal) since the last changes.yaml write, plus
    whether a delegation lacks its handoff/event entries. Empty on any problem."""
    try:
        flags, paths = H.unlogged([e for e in H.read_journal() if e.get("type") != "stop"])
        return flags, paths
    except Exception:
        return {}, {}


def collect_timestamps():
    """Every recorded timestamp across the ledgers (Timestamp + LastUpdate fields)."""
    stamps = []
    for name in ("changes.yaml", "lessons.yaml", "handoffs.yaml", "events.yaml", "decisions.yaml"):
        for _id, fields in load_ledger(name):
            if not isinstance(fields, dict):
                continue
            for key in ("Timestamp", "LastUpdate"):
                v = fields.get(key)
                if isinstance(v, str) and TS_RE.fullmatch(v.strip()):
                    stamps.append(v.strip())
    return stamps


def deliverables_status():
    """(present_count, total, [pending ids]) from the registry, globbed under the project root."""
    entries = load_ledger("deliverables.yaml")
    present = pending = 0
    pending_ids = []
    for did, fields in entries:
        if not isinstance(fields, dict):
            continue
        p = fields.get("Path")
        pats = [p] if isinstance(p, str) else (p if isinstance(p, list) else [])
        found = False
        for pat in pats:
            if not isinstance(pat, str):
                continue
            for m in glob.glob(os.path.join(PROJECT_ROOT, pat), recursive=True):
                if os.path.isfile(m):
                    found = True
                    break
            if found:
                break
        if found:
            present += 1
        else:
            pending += 1
            pending_ids.append(did)
    return present, len(entries), pending_ids


def dangling_handoffs():
    """Handoff stems with a BEGIN but no matching END."""
    stems = {}
    for hid, _ in load_ledger("handoffs.yaml"):
        if hid.endswith("-BEGIN"):
            stems.setdefault(hid[:-6], set()).add("B")
        elif hid.endswith("-END"):
            stems.setdefault(hid[:-4], set()).add("E")
    return sorted(s for s, v in stems.items() if "B" in v and "E" not in v)


def status_of(fields):
    return fields.get("Status") if isinstance(fields, dict) else None


def build():
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# Project State — generated {now} (do NOT edit; regenerated each turn-end)")
    lines.append(f"> Projection of tasks.md + {WORKAREA_REL}/*.yaml + the deliverables registry.")
    lines.append("> Those files are authoritative; this is a resume cursor, not a source of truth.")
    lines.append("")

    # ---- Focus (document order — never sorted) ----
    lines.append("## Focus")
    try:
        tpath = os.path.join(WORKAREA, "tasks.md")
        text = open(tpath, encoding="utf-8").read() if os.path.exists(tpath) else ""
        tasks, task_dates = parse_tasks(text)
        open_tasks = [t for t in tasks if is_open(t)]
        nxt = open_tasks[0] if open_tasks else None
        block = (nxt or (tasks[-1] if tasks else {})).get("heading") if tasks else None
        lines.append(f"- Active plan block: {block or 'none'}")
        if nxt:
            st = nxt["status"] or ("done" if nxt["done_box"] else "open")
            lines.append(f"- Next action: {nxt['id']} — {nxt['title']}  [{st}]")
        else:
            lines.append("- Next action: none (all tasks completed)")
    except Exception:
        task_dates = []
        open_tasks = []
        lines.append("- Active plan block: unknown")
        lines.append("- Next action: unknown")
    lines.append("")

    # ---- Open items ----
    lines.append("## Open items")
    try:
        top = ", ".join(t["id"] for t in open_tasks[:3]) or "—"
        lines.append(f"- Tasks not completed: {len(open_tasks)}  (next: {top})")
        decs = load_ledger("decisions.yaml")
        open_dec = [d for d, f in decs if status_of(f) == "OPEN"]
        evs = load_ledger("events.yaml")
        open_iss = [e for e, f in evs
                    if isinstance(f, dict) and f.get("EventType") == "ISSUE" and f.get("Status") == "OPEN"]
        dang = dangling_handoffs()
        lines.append(f"- Open decisions: {len(open_dec)}"
                     + (f" ({', '.join(open_dec)})" if open_dec else "")
                     + f" · Open issues: {len(open_iss)}"
                     + (f" ({', '.join(open_iss)})" if open_iss else "")
                     + f" · Dangling handoffs: {len(dang)}"
                     + (f" ({', '.join(dang)})" if dang else ""))
        if lint_tasks is not None:
            tpath = os.path.join(WORKAREA, "tasks.md")
            txt = open(tpath, encoding="utf-8").read() if os.path.exists(tpath) else ""
            n = len(lint_tasks(txt))
            lines.append(f"- tasks.md lint: {n} advisory issue(s)"
                         + ("" if not n else " — run tasks_lint.py / verify-integrity"))
        # archive hint: plan blocks (headings) that are fully COMPLETED and followed by a newer block
        try:
            tasks_all, _ = parse_tasks(txt if lint_tasks is not None else
                                       (open(os.path.join(WORKAREA, "tasks.md"), encoding="utf-8").read()
                                        if os.path.exists(os.path.join(WORKAREA, "tasks.md")) else ""))
            blocks = []
            for t in tasks_all:
                h = t.get("heading")
                if not blocks or blocks[-1][0] != h:
                    blocks.append([h, []])
                blocks[-1][1].append(t)
            superseded = [b for i, b in enumerate(blocks) if i < len(blocks) - 1 and all(not is_open(t) for t in b[1])]
            if superseded:
                lines.append(f"- Archivable plan blocks: {len(superseded)} fully COMPLETED and superseded "
                             f"({', '.join(str(b[0] or 'untitled') for b in superseded[:3])}) — move to "
                             "tasks-archive.md (yaml-log-entry: references/tasks.md)")
        except Exception:
            pass
    except Exception:
        lines.append("- (open-items scan unavailable)")
    lines.append("")

    # ---- Deliverables ----
    try:
        present, total, pending_ids = deliverables_status()
        lines.append(f"## Deliverables (registry: {total})")
        pend = ", ".join(pending_ids) if pending_ids else "none"
        lines.append(f"- Built: {present}/{total} · Pending: {pend}")
    except Exception:
        lines.append("## Deliverables")
        lines.append("- (registry scan unavailable)")
    lines.append("")

    # ---- Ledgers + last activity ----
    try:
        counts = {n: len(load_ledger(n + ".yaml"))
                  for n in ("changes", "decisions", "lessons", "handoffs", "events")}
        stamps = collect_timestamps() + list(task_dates)
        last = max(stamps) if stamps else "none recorded"
        lines.append(f"## Ledgers (last recorded activity: {last})")
        lines.append("- " + " · ".join(f"{n} {counts[n]}" for n in
                     ("changes", "decisions", "lessons", "handoffs", "events")))
    except Exception:
        lines.append("## Ledgers")
        lines.append("- (ledger scan unavailable)")
    lines.append("")

    # ---- Un-logged edits (from the hash journal; agent phases only) ----
    try:
        flags, paths = unlogged_edits()
        pend = []
        for cls in ("deliverable", "framework"):
            if flags.get(cls):
                lst = paths.get(cls, [])
                pend.append(f"{cls}: " + ", ".join(lst[:8]) + (" …" if len(lst) > 8 else ""))
        if flags.get("handoff"):
            pend.append("delegation without handoffs.yaml/events.yaml entries")
        lines.append("## Un-logged edits (need a changes.yaml / handoff entry)")
        lines.append("- " + (" · ".join(pend) if pend else "none"))
    except Exception:
        lines.append("## Un-logged edits")
        lines.append("- (journal unavailable)")
    lines.append("")

    # ---- Pointers ----
    lines.append("## Pointers")
    lines.append(f"- Plan → {WORKAREA_REL}/tasks.md (archive: tasks-archive.md)")
    lines.append(f"- Logs → {WORKAREA_REL}/{{changes,decisions,lessons,handoffs,events}}.yaml")
    lines.append(f"- Registry → {WORKAREA_REL}/deliverables.yaml")
    return "\n".join(lines) + "\n"


def write_state(out=OUT_DEFAULT):
    """Regenerate STATE.md; returns its content ('' on failure). Safe to call from other hooks."""
    try:
        content = build()
        os.makedirs(os.path.dirname(out), exist_ok=True)
        H.atomic_write(out, content)
        return content
    except Exception as e:
        H.log(f"refresh_state: {type(e).__name__}: {e}")
        return ""


def prune_journal(max_entries=4000, keep=1500):
    """Keep the hash journal bounded (it is runtime bookkeeping, not an audit ledger)."""
    try:
        with H.locked():
            entries = H.read_journal()
            if len(entries) > max_entries:
                import json
                H.atomic_write(H.JOURNAL, "".join(json.dumps(e, ensure_ascii=False) + "\n"
                                                  for e in entries[-keep:]))
    except Exception:
        pass


def main():
    if "--print" not in sys.argv and "--force" not in sys.argv:
        H.guard()                                    # hook mode: inert unless the project is armed
    out = OUT_DEFAULT
    if "--out" in sys.argv:
        i = sys.argv.index("--out")
        if i + 1 < len(sys.argv):
            out = sys.argv[i + 1]
    content = write_state(out)
    prune_journal()
    if "--print" in sys.argv and content:
        sys.stdout.write(content)
    sys.exit(0)  # fail-open: never wedge a turn on a generation error


if __name__ == "__main__":
    main()
