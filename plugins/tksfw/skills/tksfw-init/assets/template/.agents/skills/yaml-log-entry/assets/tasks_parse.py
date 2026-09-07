#!/usr/bin/env python3
"""Shared parser for the Activity Plan (`tasks.md`) — the ONE parsing path for the plan file,
imported by `refresh_state.py` (STATE.md), `tasks_lint.py` (R2 grammar/evidence lint) and
`cross_check.py` (R1 cross-ledger integrity). Keeping a single parser here (Group A, method tooling)
avoids the divergent regexes that a per-consumer copy would cause.

Line grammar (per `AGENTS.md § Activity Plan`), nesting via leading indent:
    - [ ] <TaskID> <Title> - <AgentName> : <OPEN|IN-PROGRESS|WAITING-FOR|COMPLETED> <YYYY-MM-DD hh:mm:ss>
A COMPLETED task MAY carry a trailing closing-evidence token:
    ... : COMPLETED <YYYY-MM-DD hh:mm:ss> [ev:<EventID>]
where <EventID> is a base62-8 id resolving to an `events.yaml` entry (validated by tasks_lint /
cross_check, not here). TaskIDs are RANDOM base62 and carry NO order — sequence/dependency is
document order (top→bottom, nested), so this parser preserves source order and never sorts.

Standard library only.
"""
import re

TS = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
TS_RE = re.compile(TS)
STATUSES = ("OPEN", "IN-PROGRESS", "WAITING-FOR", "COMPLETED")

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
TASK_RE = re.compile(r"^(\s*)-\s*\[([ xX])\]\s+(\S+)\s+(.*)$")
# status + timestamp, then an OPTIONAL trailing [ev:<base62-8>] closing-evidence token
TAIL_RE = re.compile(
    r":\s*(" + "|".join(STATUSES) + r")\s+(" + TS + r")(?:\s+\[ev:([A-Za-z0-9]{8})\])?\s*$"
)
AGENT_TAIL_RE = re.compile(r"\s*-\s*\S+\s*$")   # trailing " - <agent-token>" before the " : STATUS"


def parse_tasks(text):
    """Return (tasks, dates). `tasks` is in DOCUMENT order (never sorted). Each task is a dict:
    id, title, agent(None), status, date, ev, heading (nearest H1, else nearest heading),
    done_box (bool), indent (int), lineno (1-based), well_formed (bool — tail matched).
    `dates` is every task LastUpdateDate stamp seen (for last-activity computation)."""
    tasks, dates = [], []
    h1 = last_any = None
    for i, line in enumerate(text.splitlines(), start=1):
        hm = HEADING_RE.match(line)
        if hm:
            level, txt = len(hm.group(1)), hm.group(2).strip()
            last_any = txt
            if level == 1:
                h1 = txt
            continue
        tm = TASK_RE.match(line)
        if not tm:
            continue
        indent, box, tid, rest = tm.groups()
        status = date = ev = None
        agent = None
        title = rest
        well = False
        tl = TAIL_RE.search(rest)
        if tl:
            well = True
            status, date, ev = tl.group(1), tl.group(2), tl.group(3)
            head = rest[:tl.start()]
            am = AGENT_TAIL_RE.search(head)
            agent = am.group(1).strip() if am and am.groups() else (head.rsplit(" - ", 1)[1].strip() if " - " in head else None)
            title = AGENT_TAIL_RE.sub("", head).strip()
            dates.append(date)
        tasks.append({
            "id": tid, "title": title, "agent": agent, "status": status, "date": date, "ev": ev,
            "heading": h1 or last_any, "done_box": box.lower() == "x",
            "indent": len(indent.replace("\t", "    ")), "lineno": i, "well_formed": well,
        })
    # Leaf = a task with no deeper child following it in document order. Evidence-of-closing is
    # required at LEAF granularity (a parent's completion is implied by its leaves), so consumers
    # need this flag; compute it once here from indent + document order.
    for idx, t in enumerate(tasks):
        nxt = tasks[idx + 1] if idx + 1 < len(tasks) else None
        t["is_leaf"] = nxt is None or nxt["indent"] <= t["indent"]
    return tasks, dates


def is_open(t):
    """Not-completed by the status token when present, else by the checkbox."""
    if t["status"] is not None:
        return t["status"] != "COMPLETED"
    return not t["done_box"]


def is_completed(t):
    return not is_open(t)


def is_top_level(t):
    return t["indent"] == 0
