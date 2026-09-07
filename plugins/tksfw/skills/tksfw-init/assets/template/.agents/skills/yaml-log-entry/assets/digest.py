#!/usr/bin/env python3
"""Ledger digest — the ledgers read back as decision context (2.0.0).

    digest.py [--task <TaskID>] [--agent <name>] [--json] [--budget N]

Selection is deterministic — by status, recency and explicit IDs (TaskID, DecisionID, RelatedTo) —
never by similarity, so what an agent is shown is auditable. Sections, in priority order:

  blocked      tasks whose latest gate event (REVIEW/TEST/AUDIT/APPROVAL) is negative with no later positive
  in_force     decisions whose effective status is ACCEPTED  (title · Impact/Reversibility · Scope head)
  pending      decisions with effective status OPEN
  issues       ISSUE events with Status OPEN
  in_flight    handoffs with BEGIN and no END (title · TargetAgent · TaskID)
  lessons      most recent lessons (title · first line of Description)
  changes      most recent changes (title · Layer)

`--task T` narrows every section to entries that reference T (events.TaskID, handoffs.TaskID,
decisions.RelatedTo.Tasks, lessons/changes mentioning T) and adds the task line and its evidence chain.
`--agent A` (SubagentStart briefing) adds the latest open handoff BEGIN addressed to A, then narrows by its
TaskID. Limits come from `[state]` in .agents/models.toml (defaults below); `format_digest` truncates to
`budget_chars`, dropping lowest-priority items first. Std lib only; readers merge every shard + legacy
(+ archive for evidence chains).
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_yaml_log import load_entries   # noqa: E402
from tasks_parse import parse_tasks          # noqa: E402

SHARD_RE = re.compile(r"^(changes|lessons|handoffs|events|decisions)\.([0-9A-Za-z]{8})\.yaml$")
NEGATIVE = {("REVIEW", "FAIL"), ("TEST", "KO"), ("AUDIT", "NON-CONFORMANT"), ("APPROVAL", "NO-GO")}
POSITIVE = {("REVIEW", "PASS"), ("TEST", "OK"), ("AUDIT", "CONFORMANT"), ("APPROVAL", "GO")}
DEFAULT_LIMITS = {"lessons": 8, "decisions": 10, "issues": 10, "changes": 5, "handoffs": 10, "blocked": 10,
                  "budget_chars": 3500, "subagent_budget_chars": 4000}


# ----------------------------------------------------------------------------- loading
def workarea(root=None):
    root = root or os.environ.get("TKSFW_PROJECT_ROOT")
    if root:
        return os.path.join(root, ".agents", "workarea")
    cur = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(cur, ".agents", "workarea")):
            return os.path.join(cur, ".agents", "workarea")
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.join(os.getcwd(), ".agents", "workarea")
        cur = parent


def limits(wa):
    out = dict(DEFAULT_LIMITS)
    try:
        import tomllib
        with open(os.path.join(os.path.dirname(os.path.dirname(wa)), ".agents", "models.toml"), "rb") as fh:
            st = tomllib.load(fh).get("state") or {}
        for k in out:
            if isinstance(st.get(k), int) and st[k] >= 0:
                out[k] = st[k]
    except Exception:
        pass
    return out


def load_kind(kind, wa, archive=False):
    paths = [os.path.join(wa, f"{kind}.yaml")]
    try:
        paths += [os.path.join(wa, n) for n in sorted(os.listdir(wa)) if SHARD_RE.match(n) and n.startswith(kind + ".")]
    except FileNotFoundError:
        pass
    if archive:
        paths.append(os.path.join(wa, "archive", f"{kind}.yaml"))
    out = []
    for p in paths:
        if os.path.isfile(p):
            try:
                out += [(e, f) for e, f in load_entries(p)[0] if isinstance(f, dict)]
            except Exception:
                pass
    return out


def ts_of(f):
    return str(f.get("Timestamp") or f.get("LastUpdate") or "")


def first_line(v, n=90):
    s = str(v or "").strip().splitlines()
    return (s[0][:n] + ("…" if s and len(s[0]) > n else "")) if s else ""


def joined(v, n=200):
    """All lines of a memo/list joined with '; ' (block lists lose their dashes), capped at n chars."""
    if isinstance(v, list):
        parts = [str(x) for x in v]
    else:
        parts = [l.strip().lstrip("- ").strip() for l in str(v or "").splitlines() if l.strip()]
    out = "; ".join(parts)
    return out[:n] + ("…" if len(out) > n else "")


# ----------------------------------------------------------------------------- model
def build(wa, task=None, agent=None, archive_evidence=True):
    """Structured digest. Every item is a dict with 'id', 'line' (formatted) and source fields."""
    ev = load_kind("events", wa)
    dec = load_kind("decisions", wa)
    ho = load_kind("handoffs", wa)
    les = load_kind("lessons", wa)
    chg = load_kind("changes", wa)
    d = {"task": task, "agent": agent, "handoff": None, "blocked": [], "in_force": [], "pending": [],
         "issues": [], "in_flight": [], "lessons": [], "changes": [], "task_line": None, "evidence": []}

    # agent briefing: latest open BEGIN addressed to the agent → narrows by its TaskID
    if agent:
        ends = {h.rsplit("-", 1)[0] for h, _ in ho if h.endswith("-END")}
        begins = sorted(((ts_of(f), h, f) for h, f in ho if h.endswith("-BEGIN") and str(f.get("TargetAgent")) == agent
                         and h.rsplit("-", 1)[0] not in ends), reverse=True)
        if begins:
            _t, h, f = begins[0]
            d["handoff"] = {"id": h, "title": str(f.get("Title", "")), "task": str(f.get("TaskID", "")),
                            "scope": joined(f.get("Scope"), 120), "inputs": joined(f.get("Inputs"), 200),
                            "description": joined(f.get("Description"), 240)}
            if not task and f.get("TaskID") and f.get("TaskID") != "N/A":
                task = d["task"] = str(f["TaskID"])

    def mentions(f, keys=("Description", "Remarks", "Rationale", "Scope", "Title")):
        return bool(task) and any(task in str(f.get(k, "")) for k in keys)

    # effective decision status
    eff = {i: str(f.get("Status", "")) for i, f in dec}
    trans = {}
    for _e, f in ev:
        if f.get("EventType") == "DECISION" and f.get("DecisionID") in eff:
            t = ts_of(f)
            if t >= trans.get(f["DecisionID"], ("", ""))[0]:
                trans[f["DecisionID"]] = (t, str(f.get("Status")))
    for i, (_t, st) in trans.items():
        eff[i] = st

    def dec_related(f):
        rel = f.get("RelatedTo") if isinstance(f.get("RelatedTo"), dict) else {}
        tasks = rel.get("Tasks") if isinstance(rel.get("Tasks"), list) else []
        return (not task) or task in [str(x) for x in tasks] or mentions(f)

    briefing = bool(agent)
    for i, f in sorted(dec, key=lambda x: ts_of(x[1]), reverse=True):
        if not dec_related(f) and not (briefing and eff.get(i) == "ACCEPTED"):
            continue                                        # in-force decisions are global constraints for a Worker
        item = {"id": i, "title": str(f.get("Title", "")), "impact": str(f.get("Impact", "")),
                "rev": str(f.get("Reversibility", "")), "scope": first_line(f.get("Scope"), 70), "status": eff.get(i, "")}
        item["line"] = f"{i} “{item['title']}” · {item['impact']}/{item['rev']}" + (f" · {item['scope']}" if item["scope"] else "")
        if eff.get(i) == "ACCEPTED":
            d["in_force"].append(item)
        elif eff.get(i) == "OPEN":
            d["pending"].append(item)

    # issues + gates
    by_task_gate = {}
    for i, f in sorted(ev, key=lambda x: ts_of(x[1])):
        et, st, tid = str(f.get("EventType")), str(f.get("Status")), str(f.get("TaskID", ""))
        if task and tid != task and not mentions(f):
            continue
        if et == "ISSUE" and st == "OPEN":
            d["issues"].append({"id": i, "title": str(f.get("Title", "")), "task": tid, "ts": ts_of(f),
                                "line": f"{i} “{str(f.get('Title', ''))}” · task {tid} · {ts_of(f)[:10]}"})
        if (et, st) in NEGATIVE:
            by_task_gate[(tid, et)] = ("neg", i, f)
        elif (et, st) in POSITIVE:
            by_task_gate[(tid, et)] = ("pos", i, f)
    for (tid, et), (kind, i, f) in sorted(by_task_gate.items()):
        if kind == "neg":
            d["blocked"].append({"id": i, "task": tid, "gate": et, "status": str(f.get("Status")), "title": str(f.get("Title", "")),
                                 "line": f"task {tid}: {et} {f.get('Status')} — {i} “{str(f.get('Title', ''))}” ({ts_of(f)[:10]})"})
    d["issues"].reverse()

    # in-flight handoffs
    ends = {h.rsplit("-", 1)[0] for h, _ in ho if h.endswith("-END")}
    for h, f in sorted(ho, key=lambda x: ts_of(x[1]), reverse=True):
        if not h.endswith("-BEGIN") or h.rsplit("-", 1)[0] in ends:
            continue
        if task and str(f.get("TaskID", "")) != task:
            continue
        d["in_flight"].append({"id": h, "title": str(f.get("Title", "")), "target": str(f.get("TargetAgent", "")), "task": str(f.get("TaskID", "")),
                               "line": f"{h} “{str(f.get('Title', ''))}” → {f.get('TargetAgent')} · task {f.get('TaskID')}"})

    for i, f in sorted(les, key=lambda x: ts_of(x[1]), reverse=True):
        if task and not mentions(f) and not briefing:
            continue                                        # a Worker gets the recent lessons regardless of task
        d["lessons"].append({"id": i, "title": str(f.get("Title", "")), "head": first_line(f.get("Description")),
                             "line": f"{i} “{str(f.get('Title', ''))}”" + (f" — {first_line(f.get('Description'))}" if f.get("Description") else "")})
    for i, f in sorted(chg, key=lambda x: ts_of(x[1]), reverse=True):
        if task and not mentions(f):
            continue
        d["changes"].append({"id": i, "title": str(f.get("Title", "")), "layer": str(f.get("Layer", "")),
                             "line": f"{i} “{str(f.get('Title', ''))}” · {f.get('Layer')} · {ts_of(f)[:10]}"})

    # task line + evidence chain
    if task:
        for name in ("tasks.md", os.path.join("archive", "tasks.md"), "tasks-archive.md"):
            p = os.path.join(wa, name)
            if os.path.isfile(p):
                for t in parse_tasks(open(p, encoding="utf-8").read())[0]:
                    if t["id"] == task:
                        d["task_line"] = f"{t['id']} “{t['title']}” · {t.get('agent') or '-'} · {t['status'] or ('COMPLETED' if t['done_box'] else 'OPEN')} · {t.get('date') or ''}" + (f" · [ev:{t['ev']}]" if t.get("ev") else "") + ("" if name == "tasks.md" else " · archived")
        allev = load_kind("events", wa, archive=archive_evidence) if archive_evidence else ev
        d["evidence"] = [f"{i} {f.get('EventType')}/{f.get('Status')} “{str(f.get('Title', ''))}” ({ts_of(f)[:10]})"
                         for i, f in sorted(allev, key=lambda x: ts_of(x[1])) if str(f.get("TaskID", "")) == task]
    return d


# ----------------------------------------------------------------------------- formatting
SECTIONS = [  # (key, heading, limit key)
    ("blocked", "Blocked gates (latest gate negative, no later positive)", "blocked"),
    ("in_force", "Decisions in force (ACCEPTED — respect them; contradicting one requires a SUPERSEDED transition first)", "decisions"),
    ("pending", "Pending decisions (OPEN — need judgement)", "decisions"),
    ("issues", "Open issues", "issues"),
    ("in_flight", "Work in flight (handoff BEGIN without END)", "handoffs"),
    ("lessons", "Recent lessons", "lessons"),
    ("changes", "Recent changes", "changes"),
]


def format_digest(d, lim, budget=None, heading_level="###", title="Ledger digest"):
    """Markdown within `budget` chars: sections in priority order; lowest-priority items dropped first."""
    budget = budget or lim.get("budget_chars", 3500)
    blocks = []
    if d.get("handoff"):
        h = d["handoff"]
        blocks.append((0, [f"{heading_level} Your handoff: {h['id']} “{h['title']}” · task {h['task']}",
                           *( [f"- Scope: {h['scope']}"] if h["scope"] else []),
                           *( [f"- Inputs: {h['inputs']}"] if h["inputs"] else []),
                           *( [f"- Spec: {h['description']}"] if h["description"] else [])]))
    if d.get("task"):
        lines = [f"{heading_level} Task {d['task']}"]
        if d.get("task_line"):
            lines.append("- " + d["task_line"])
        if d.get("evidence"):
            lines.append("- Evidence chain: " + "; ".join(d["evidence"][-6:]))
        blocks.append((0, lines))
    for prio, (key, heading, lk) in enumerate(SECTIONS, 1):
        items = d.get(key) or []
        if not items:
            continue
        n = lim.get(lk, 10)
        lines = [f"{heading_level} {heading}"] + ["- " + it["line"] for it in items[:n]]
        if len(items) > n:
            lines.append(f"- … {len(items) - n} more (`ks ledger digest`)")
        blocks.append((prio, lines))
    if not blocks:
        return ""
    # fit to budget: trim items from the lowest-priority block upwards
    def render(bl):
        return "\n".join(l for _p, ls in bl for l in ls) + "\n"
    text = render(blocks)
    while len(text) > budget and blocks:
        # find the lowest-priority block with more than the heading line
        for idx in range(len(blocks) - 1, -1, -1):
            prio, ls = blocks[idx]
            if len(ls) > 1:
                ls.pop()                                     # drop last item
                if len(ls) == 1:
                    blocks.pop(idx)
                break
        else:
            break
        text = render(blocks)
    return text


def main():
    a = sys.argv[1:]
    if "-h" in a or "--help" in a:
        print(__doc__)
        sys.exit(0)
    task = a[a.index("--task") + 1] if "--task" in a else None
    agent = a[a.index("--agent") + 1] if "--agent" in a else None
    wa = workarea()
    lim = limits(wa)
    budget = int(a[a.index("--budget") + 1]) if "--budget" in a else None
    d = build(wa, task=task, agent=agent)
    if "--json" in a:
        print(json.dumps(d, indent=2, ensure_ascii=False))
        sys.exit(0)
    text = format_digest(d, lim, budget)
    print(text if text else "(nothing to report — no decisions, issues, open handoffs, lessons or changes" + (f" for task {task}" if task else "") + ")")


if __name__ == "__main__":
    main()
