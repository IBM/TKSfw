#!/usr/bin/env python3
"""Export the project's ledgers as a formatted Excel workbook (or CSV files) — std lib only.

    export_ledgers.py all                       [--out FILE] [--archive] [--session TOKEN] [--csv DIR]
    export_ledgers.py changes,events[,…]        same options; kinds: changes lessons handoffs events
                                                decisions deliverables tasks

Sheets: Summary (project, version, generated, operator, counts, sessions) + one sheet per requested kind.
Rows merge every session shard and the legacy file; --archive adds the cumulative archives (column
`Archived`). Columns: EntryID, the schema fields in schema order, then Session (shard token), Source (file),
Archived. Extra columns: handoffs Stem/Half; decisions EffectiveStatus (latest DECISION event); events
DecisionID; deliverables Present; tasks Block/Level/Parent/Evidence. Header bold + frozen, autofilter,
memo fields wrapped, timestamps as real Excel datetimes, IDs kept as text.

Default output: .agents/workarea/exports/ledgers-<YYYYMMDD-HHMM>.xlsx (never watched, never a deliverable).
Exit 0 written · 1 nothing to export · 2 error.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import csv
import json
import glob
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_yaml_log import load_entries, SCHEMAS, OWNER_FIELDS   # noqa: E402
from tasks_parse import parse_tasks                                 # noqa: E402
import xlsx_lite                                                     # noqa: E402

KINDS = ("changes", "lessons", "handoffs", "events", "decisions", "deliverables", "tasks")
SHARDED = ("changes", "lessons", "handoffs", "events", "decisions")
SHARD_RE = re.compile(r"^(changes|lessons|handoffs|events|decisions)\.([0-9A-Za-z]{8})\.yaml$")
MEMO = {"Description", "StateBefore", "StateAfter", "Remarks", "Rationale", "Implications", "Alternatives",
        "Inputs", "Outputs", "RelatedTo"}
WIDTHS = {"EntryID": 12, "Title": 48, "AuthorAgent": 16, "TargetAgent": 16, "Model": 18, "Layer": 10,
          "Status": 12, "EventType": 11, "TaskID": 11, "EventID": 11, "DecisionID": 11, "Session": 11,
          "Source": 24, "Archived": 9, "Description": 60, "StateBefore": 40, "StateAfter": 40, "Remarks": 40,
          "Rationale": 50, "Implications": 40, "Alternatives": 40, "Scope": 30, "Impact": 9, "Reversibility": 12,
          "ConfirmationType": 14, "OwnerSessionId": 12, "OwnerSessionUserName": 18, "Path": 40, "Present": 9,
          "Stem": 11, "Half": 7, "EffectiveStatus": 14, "Block": 30, "Level": 6, "Parent": 11, "Evidence": 11,
          "Agent": 16, "LastUpdate": 19, "Timestamp": 19}


def project_root():
    p = os.environ.get("TKSFW_PROJECT_ROOT")
    if p:
        return os.path.abspath(p)
    cur = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(cur, ".agents", "workarea")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            sys.exit("no .agents/workarea found upward from cwd (set TKSFW_PROJECT_ROOT)")
        cur = parent


def files_for(kind, wa, archive, session):
    """[(path, token|'' , archived)] for a kind."""
    out = []
    if kind in SHARDED:
        legacy = os.path.join(wa, f"{kind}.yaml")
        if os.path.isfile(legacy) and not session:
            out.append((legacy, "", False))
        for n in sorted(os.listdir(wa)) if os.path.isdir(wa) else []:
            m = SHARD_RE.match(n)
            if m and m.group(1) == kind and (not session or m.group(2) == session):
                out.append((os.path.join(wa, n), m.group(2), False))
        a = os.path.join(wa, "archive", f"{kind}.yaml")
        if archive and os.path.isfile(a) and not session:
            out.append((a, "", True))
    elif kind == "deliverables":
        p = os.path.join(wa, "deliverables.yaml")
        if os.path.isfile(p):
            out.append((p, "", False))
    return out


def scalar(v):
    """Cell text for a field value: scalars as-is, mappings/lists as compact readable text."""
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, list):
        return "\n".join(scalar(x) if not isinstance(x, (dict, list)) else json.dumps(x, ensure_ascii=False) for x in v)
    if isinstance(v, dict):
        return "\n".join(f"{k}: " + (", ".join(str(x) for x in val) if isinstance(val, list) else str(val)) for k, val in v.items())
    return str(v)


def ledger_sheet(kind, wa, archive, session, effective=None):
    schema = SCHEMAS[kind]
    fields = list(schema["required"]) + [f for f in schema.get("optional", ()) if f not in schema["required"]]
    for f in sorted(OWNER_FIELDS):
        if f not in fields:
            fields.append(f)
    extra = []
    if kind == "handoffs":
        extra = ["Stem", "Half"]
    if kind == "decisions":
        extra = ["EffectiveStatus"]
    if kind == "deliverables":
        extra = ["Present"]
    header = ["EntryID"] + fields + extra + (["Session", "Source", "Archived"] if kind != "deliverables" else ["Source"])
    rows = []
    root = os.path.dirname(os.path.dirname(os.path.dirname(wa)))
    for path, token, archived in files_for(kind, wa, archive, session):
        try:
            entries, _ = load_entries(path)
        except Exception:
            continue
        src = os.path.relpath(path, wa)
        for eid, f in entries:
            f = f if isinstance(f, dict) else {}
            row = [eid] + [scalar(f.get(x)) for x in fields]
            if kind == "handoffs":
                stem, _, half = eid.rpartition("-")
                row += [stem or eid, half]
            if kind == "decisions":
                row += [(effective or {}).get(eid, f.get("Status", ""))]
            if kind == "deliverables":
                pats = f.get("Path")
                pats = [pats] if isinstance(pats, str) else (pats if isinstance(pats, list) else [])
                present = any(os.path.isfile(m) for p in pats if isinstance(p, str) for m in glob.glob(os.path.join(root, p), recursive=True))
                row += [present]
            row += ([token or ("archive" if archived else "legacy"), src, archived] if kind != "deliverables" else [src])
            rows.append(row)
    dts = {"Timestamp", "LastUpdate"} & set(header)
    return header, rows, dts


def tasks_sheet(wa, archive):
    header = ["TaskID", "Title", "Agent", "Status", "LastUpdate", "Evidence", "Block", "Level", "Parent", "Source", "Archived"]
    rows = []
    files = [(os.path.join(wa, "tasks.md"), False)]
    if archive:
        files += [(os.path.join(wa, "archive", "tasks.md"), True), (os.path.join(wa, "tasks-archive.md"), True)]
    for path, archived in files:
        if not os.path.isfile(path):
            continue
        tasks, _ = parse_tasks(open(path, encoding="utf-8").read())
        stack = []                                    # (indent, id) for parent resolution
        for t in tasks:
            while stack and stack[-1][0] >= t["indent"]:
                stack.pop()
            parent = stack[-1][1] if stack else ""
            stack.append((t["indent"], t["id"]))
            rows.append([t["id"], t["title"], t.get("agent") or "", t["status"] or ("COMPLETED" if t["done_box"] else "OPEN"),
                         t.get("date") or "", t.get("ev") or "", t.get("heading") or "", len(stack), parent,
                         os.path.relpath(path, wa), archived])
    return header, rows, {"LastUpdate"}


def effective_decisions(wa, archive, session):
    """{decision_id: status} from the latest DECISION event carrying DecisionID."""
    eff = {}
    trans = {}
    for path, _t, _a in files_for("events", wa, archive, None):
        try:
            entries, _ = load_entries(path)
        except Exception:
            continue
        for eid, f in entries:
            if isinstance(f, dict) and f.get("EventType") == "DECISION" and f.get("DecisionID"):
                ts = str(f.get("Timestamp", ""))
                if ts >= trans.get(f["DecisionID"], ("", ""))[0]:
                    trans[f["DecisionID"]] = (ts, str(f.get("Status")))
    for d, (_ts, st) in trans.items():
        eff[d] = st
    return eff


def summary_rows(root, wa, kinds, counts, archive, session):
    rows = [["Project", root], ["Generated", time.strftime("%Y-%m-%d %H:%M:%S")]]
    try:
        m = json.load(open(os.path.join(root, ".agents", ".tksfw.json")))
        rows.append(["Framework version", m.get("version", "?")])
    except Exception:
        pass
    rows.append(["Operator", os.environ.get("TKSFW_USER", "") or _operator()])
    rows.append(["Archive included", "yes" if archive else "no"])
    if session:
        rows.append(["Session filter", session])
    rows.append(["", ""])
    rows.append(["Sheet", "Rows"])
    for k in kinds:
        rows.append([k, counts.get(k, 0)])
    rows.append(["", ""])
    rows.append(["Session", "Operator · entries · last seen"])
    sess = {}
    d = os.path.join(wa, ".hook-state", "sessions")
    try:
        for f in os.listdir(d):
            if f.endswith(".json"):
                rec = json.load(open(os.path.join(d, f)))
                sess[rec["token"]] = rec
    except Exception:
        pass
    per = {}
    for k in SHARDED:
        for n in os.listdir(wa) if os.path.isdir(wa) else []:
            mm = SHARD_RE.match(n)
            if mm and mm.group(1) == k:
                try:
                    per[mm.group(2)] = per.get(mm.group(2), 0) + len(load_entries(os.path.join(wa, n))[0])
                except Exception:
                    pass
    for tok in sorted(set(per) | set(sess)):
        rec = sess.get(tok, {})
        seen = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(rec["last_seen"]))) if rec.get("last_seen") else "—"
        rows.append([tok, f"{rec.get('operator') or '?'} · {per.get(tok, 0)} entries · {seen}"])
    return rows


def _operator():
    cfg = os.path.join(os.environ.get("TKSFW_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "tksfw"), "user.toml")
    try:
        for line in open(cfg, encoding="utf-8"):
            m = re.match(r'^\s*name\s*=\s*"([^"]*)"', line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return ""


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    what = a[0]
    kinds = list(KINDS) if what == "all" else [k.strip() for k in what.split(",") if k.strip()]
    for k in kinds:
        if k not in KINDS:
            sys.exit(f"unknown kind {k!r} — one of: all, {', '.join(KINDS)}")
    archive = "--archive" in a
    session = a[a.index("--session") + 1] if "--session" in a else None
    out = a[a.index("--out") + 1] if "--out" in a else None
    csv_dir = a[a.index("--csv") + 1] if "--csv" in a else None
    root = project_root()
    wa = os.path.join(root, ".agents", "workarea")
    eff = effective_decisions(wa, archive, session) if "decisions" in kinds else {}
    sheets, counts = [], {}
    for k in kinds:
        if k == "tasks":
            header, rows, dts = tasks_sheet(wa, archive)
        else:
            header, rows, dts = ledger_sheet(k, wa, archive, session, eff)
        counts[k] = len(rows)
        sheets.append((k, header, rows, dts))
    if not any(counts.values()):
        print("nothing to export (no entries found)")
        sys.exit(1)
    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)
        for k, header, rows, _ in sheets:
            with open(os.path.join(csv_dir, f"{k}.csv"), "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(header)
                w.writerows(rows)
        print(f"csv → {csv_dir} ({', '.join(f'{k} {counts[k]}' for k in kinds)})")
        sys.exit(0)
    if not out:
        os.makedirs(os.path.join(wa, "exports"), exist_ok=True)
        out = os.path.join(wa, "exports", f"ledgers-{time.strftime('%Y%m%d-%H%M')}.xlsx")
    wb = xlsx_lite.Workbook()
    wb.add_sheet("Summary", ["Item", "Value"], summary_rows(root, wa, kinds, counts, archive, session),
                 widths={"Item": 22, "Value": 80}, autofilter=False)
    for k, header, rows, dts in sheets:
        wb.add_sheet(k, header, rows, widths=WIDTHS, wrap=MEMO, datetimes=dts)
    wb.save(out)
    print(f"xlsx → {out}  (" + ", ".join(f"{k} {counts[k]}" for k in kinds) + ")")
    sys.exit(0)


if __name__ == "__main__":
    main()
