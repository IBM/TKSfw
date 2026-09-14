#!/usr/bin/env python3
"""Project layers (2.2.0, names since 3.6.0): the ONE resolver for the ARCHETYPE and SPEC files.

    layers.py resolve [--archetype P] [--spec P] [--json]   where the layers are, their status (exit 0/3/4)
    layers.py pin --archetype P | --spec P [--clear]        record paths in .agents/.tksfw.json `layers`
    layers.py journal                                       record the current hashes (status baseline)
    layers.py section                                       the markdown block the SessionStart hook injects

The layer model: CORE (AGENTS.md — principles, orchestration policy, agent behaviour, execution
guidelines, acceptance criteria) · ARCHETYPE (`KS_PROJECT.md` — what kind of project this is and how
such projects are run; changes.yaml `Layer: ARCHETYPE`) · PROJECT SPEC (`KS_SPEC.md` — what this
particular project must deliver; `Layer: PROJECT`). Names, not numbers (ADR 0016).

Convention (tier 3): the two files at the project root. Declared paths (tier 2): `"layers":
{"archetype": "...", "spec": "..."}` in `.agents/.tksfw.json`, relative to the project root (the
pre-3.6.0 keys `l3` / `l4` and flags `--l3` / `--l4` are still accepted). Explicit arguments (tier 1)
win over both for the key they name. A declared path that does not exist resolves as `missing` —
never a silent fallback to the convention. The archetype is optional (a project may have only a
spec); both keys may point at the same file.

Consumers — the SessionStart hook (`inject_state.py`), the `ks-start` skill (through `ks layers
resolve --json`) and any later launcher — call this module; none of them restates the tiers.

Status is relative to the last recorded hashes (`.hook-state/hosts/<host>/layers.json`, written by
`journal` — the SessionStart hook and the `ks-start` skill call it): `new` (never recorded),
`unchanged`, `changed` (the drift signal: re-read), `missing` (declared but absent). Hashes use
the framework's hash journal algorithm (`hooklib.sha256_file`). Standard library only.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402

CONVENTION = H.LAYER_CONVENTION            # single source: hooklib (classify/watched_files use it too)
LAYER_ORDER = ("archetype", "spec")
LABEL = {"archetype": "Archetype", "spec": "Spec"}
LEDGER_LAYER = {"archetype": "ARCHETYPE", "spec": "PROJECT"}     # changes.yaml Layer value for edits
LEGACY = H.LAYER_LEGACY_KEYS                                    # {"l3": "archetype", "l4": "spec"}
KS_LAYER_VALUES = {"archetype": ("project", "archetype", "l3"), "spec": ("spec", "project-spec", "l4")}
RECORD = os.path.join(H.STATE_DIR, "layers.json")
SECTION_CAP = 600                      # bytes: the block is pointers, never content
STATUS_TEXT = {
    "new": "new, not yet journaled",
    "unchanged": "unchanged",
    "changed": "changed since last session",
    "missing": "declared in .agents/.tksfw.json but missing",
}
_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)


# ----------------------------------------------------------------------------- paths
def valid_rel(path):
    """A project-relative path is acceptable when it is relative, stays inside the root and ends
    in .md. Returns the normalised rel or None."""
    if not isinstance(path, str) or not path.strip():
        return None
    p = path.strip().replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:/", p):
        return None
    if p.startswith("./"):
        p = p[2:]
    if any(seg == ".." for seg in p.split("/")) or not p.lower().endswith(".md"):
        return None
    return p


def declared():
    """{'archetype': rel|None, 'spec': rel|None, 'watch': bool, 'invalid': {key: raw}} from the manifest
    (legacy keys l3/l4 honoured)."""
    m = H.read_manifest() or {}
    lay = m.get("layers") if isinstance(m.get("layers"), dict) else {}
    out = {"archetype": None, "spec": None, "watch": lay.get("watch", True) is not False, "invalid": {}}
    for k in LAYER_ORDER:
        raw = H.layer_stanza_value(lay, k)
        if raw is None:
            continue
        rel = valid_rel(raw)
        if rel is None:
            out["invalid"][k] = raw
        else:
            out[k] = rel
    return out


def layer_paths():
    """{'archetype': rel, 'spec': rel} as the hooks see them (tiers 2 + 3, no arguments) — the watched set.
    Declared paths are returned even when the file is absent (so their appearance is journaled)."""
    d = declared()
    return {k: (d[k] or CONVENTION[k]) for k in LAYER_ORDER}


# ----------------------------------------------------------------------------- files
def parse_frontmatter(text):
    """(frontmatter dict|None, warning|None) — minimal `key: value` YAML subset, no dependency."""
    m = _FM_RE.match(text)
    if not m:
        return None, None
    fm = {}
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        mm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not mm:
            return None, f"frontmatter line not `key: value`: {line.strip()[:40]!r}"
        k, v = mm.group(1), mm.group(2).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        elif re.fullmatch(r"-?\d+", v):
            v = int(v)
        fm[k] = v
    return fm, None


def title_of(text, fm):
    if isinstance(fm, dict) and isinstance(fm.get("title"), str) and fm["title"].strip():
        return fm["title"].strip()
    body = _FM_RE.sub("", text, count=1)
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else ""


def read_record():
    return H.load_json(RECORD, {}) or {}


def resolve(archetype=None, spec=None):
    """The resolution result (see module doc). Never raises; problems land in `warnings`."""
    d = declared()
    warnings = [f"{k}: invalid path in .agents/.tksfw.json ignored: {v!r}" for k, v in d["invalid"].items()]
    args = {"archetype": archetype, "spec": spec}
    rec = read_record()
    layers, tiers = [], set()
    for k in LAYER_ORDER:
        if args[k]:
            rel, source = valid_rel(args[k]), "args"
            if rel is None:
                warnings.append(f"{k}: argument is not a project-relative .md path: {args[k]!r}")
                continue
        elif d[k]:
            rel, source = d[k], "config"
        else:
            rel, source = CONVENTION[k], "convention"
        path = os.path.join(H.PROJECT_ROOT, rel)
        exists = os.path.isfile(path)
        if not exists and source == "convention":
            continue                                   # optional layer, not declared: simply absent
        entry = {"layer": k, "label": LABEL[k], "ledger_layer": LEDGER_LAYER[k], "path": rel, "source": source, "exists": exists, "hash": None,
                 "journal_status": "missing", "title": "", "frontmatter": None}
        if exists:
            try:
                entry["hash"] = H.sha256_file(path)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                fm, warn = parse_frontmatter(text)
                if warn:
                    warnings.append(f"{k} ({rel}): {warn}")
                entry["frontmatter"] = fm
                entry["title"] = title_of(text, fm)
                if isinstance(fm, dict) and "ks_layer" in fm and str(fm["ks_layer"]) not in KS_LAYER_VALUES[k]:
                    warnings.append(f"{k} ({rel}): frontmatter declares ks_layer={fm['ks_layer']!r} but the file is resolved as {LABEL[k]}")
                prev = rec.get(rel) or {}
                if not prev.get("hash"):
                    entry["journal_status"] = "new"
                else:
                    entry["journal_status"] = "unchanged" if prev["hash"] == entry["hash"] else "changed"
            except Exception as e:
                warnings.append(f"{k} ({rel}): unreadable: {type(e).__name__}: {e}")
                entry["journal_status"] = "missing"
                entry["exists"] = False
        layers.append(entry)
        tiers.add(source)
    tier = "none"
    for t in ("args", "config", "convention"):
        if t in tiers:
            tier = t
            break
    return {"project_root": H.PROJECT_ROOT, "tier": tier, "layers": layers, "warnings": warnings,
            "watch": d["watch"]}


def exit_code(res):
    """0 a layer file was found; 3 nothing resolved; 4 a declared layer is missing."""
    if any(e["journal_status"] == "missing" for e in res["layers"]):
        return 4
    if not any(e["exists"] for e in res["layers"]):
        return 3
    return 0


# ----------------------------------------------------------------------------- side effects
def journal(res=None):
    """Record the current hashes of the resolved, existing layers (the status baseline)."""
    res = res or resolve()
    rec = read_record()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    for e in res["layers"]:
        if e["exists"] and e["hash"]:
            rec[e["path"]] = {"hash": e["hash"], "ts": ts, "layer": e["layer"]}
    H.ensure_state_dir()
    H.atomic_write(RECORD, json.dumps(rec, indent=1, sort_keys=True))
    return rec


def pin(archetype=None, spec=None, clear=False):
    """Write/clear the `layers` stanza in .agents/.tksfw.json (keys archetype/spec; a legacy l3/l4 key for
    the same layer is replaced). Returns the stanza written (or None)."""
    m = H.read_manifest()
    if m is None:
        raise SystemExit("no .agents/.tksfw.json — initialise the project first (ks project init)")
    if clear:
        m.pop("layers", None)
        stanza = None
    else:
        stanza = dict(m.get("layers") or {}) if isinstance(m.get("layers"), dict) else {}
        for k, v in (("archetype", archetype), ("spec", spec)):
            if v is None:
                continue
            rel = valid_rel(v)
            if rel is None:
                raise SystemExit(f"{k}: not a project-relative .md path inside the project: {v!r}")
            stanza[k] = rel
            for old, new in LEGACY.items():
                if new == k:
                    stanza.pop(old, None)
        if not stanza:
            raise SystemExit("usage: layers.py pin --archetype <path> | --spec <path> | --clear")
        m["layers"] = stanza
    H.atomic_write(H.MANIFEST, json.dumps(m, indent=2, sort_keys=True) + "\n")
    return stanza


# ----------------------------------------------------------------------------- emitter
def section(res=None):
    """Markdown pointer block for the SessionStart injection, '' when nothing resolves.
    Bounded by SECTION_CAP; carries paths and statuses, never content or hashes."""
    res = res or resolve()
    if not res["layers"]:
        return ""
    rows = ["| Layer | File | Status |", "|---|---|---|"]
    hints = []
    for e in res["layers"]:
        rows.append(f"| {LABEL[e['layer']]} | `{e['path']}` | {STATUS_TEXT[e['journal_status']]} |")
        if e["journal_status"] == "changed":
            hints.append("Re-read changed layers; do not rely on earlier context.")
        elif e["journal_status"] == "missing":
            hints.append("Fix or remove the declaration (`ks layers pin`) before `/ks-start`.")
    have = [e["layer"] for e in res["layers"] if e["exists"]]
    order = " then ".join(LABEL[k] for k in LAYER_ORDER if k in have) or "them"
    text = ("## Project layers\n" + "\n".join(rows) + f"\nRead {order} in full before planning. "
            "Spec overrides Archetype; neither overrides AGENTS.md (Core). Start execution with `/ks-start`."
            + (" " + " ".join(dict.fromkeys(hints)) if hints else ""))
    if len(text.encode("utf-8")) > SECTION_CAP:
        text = text.encode("utf-8")[: SECTION_CAP - 2].decode("utf-8", "ignore") + " …"
    return text


# ----------------------------------------------------------------------------- CLI
def _opt(args, name):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
        raise SystemExit(f"{name} needs a value")
    return None


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    sub, rest = argv[0], argv[1:]
    if sub == "resolve":
        res = resolve(_opt(rest, "--archetype") or _opt(rest, "--l3"), _opt(rest, "--spec") or _opt(rest, "--l4"))
        rc = exit_code(res)
        if "--json" in rest:
            print(json.dumps(res, indent=2))
        else:
            if not res["layers"]:
                print("no project layers: nothing at KS_PROJECT.md (archetype) / KS_SPEC.md (spec) and no `layers` in .agents/.tksfw.json")
            for e in res["layers"]:
                print(f"{LABEL[e['layer']]:<9}  {e['path']}  [{e['source']}]  {STATUS_TEXT[e['journal_status']]}"
                      + (f"  — {e['title']}" if e["title"] else ""))
            for w in res["warnings"]:
                print("warning:", w)
        return rc
    if sub == "journal":
        res = resolve()
        journal(res)
        print(f"layers journaled: {', '.join(e['path'] for e in res['layers'] if e['exists']) or 'none'} → {os.path.relpath(RECORD, H.PROJECT_ROOT)}")
        return exit_code(res)
    if sub == "pin":
        stanza = pin(_opt(rest, "--archetype") or _opt(rest, "--l3"), _opt(rest, "--spec") or _opt(rest, "--l4"), clear="--clear" in rest)
        print("layers cleared from .agents/.tksfw.json (convention applies)" if stanza is None
              else "layers pinned in .agents/.tksfw.json: " + json.dumps(stanza))
        return 0
    if sub == "section":
        sys.stdout.write(section())
        return 0
    raise SystemExit("usage: layers.py resolve [--archetype P] [--spec P] [--json] | pin --archetype P | --spec P | --clear | journal | section")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
