#!/usr/bin/env python3
"""Validate the project's YAML files against `references/schemas.md` (§ YAML-based Logs /
§ Deliverables Registry).

Four append-only LEDGER kinds live under `.claude/workarea/`:
  changes   -> changes.yaml    (ChangeID  -> AuthorAgent, Model, Timestamp, Layer,
                                 Title, Description, StateBefore, StateAfter, Remarks;
                                 Layer is the enum CORE|ARCHETYPE|PROJECT (legacy METHOD accepted) — see
                                 `_validate_change`)
  lessons   -> lessons.yaml     (LessonID  -> AuthorAgent, Model, Timestamp, Title,
                                 Description, Remarks)
  handoffs  -> handoffs.yaml    (<base62-8>-<BEGIN|END> -> EventID, TaskID, AuthorAgent,
                                 TargetAgent, Timestamp, Title, Description, Scope,
                                 Inputs.Files, Outputs.{Files, Summary, CandidateLessons})
  events    -> events.yaml      (EventID   -> TaskID, AuthorAgent, Model, Timestamp,
                                 EventType, Title, Remarks, Status)

Plus one mutable REGISTRY kind (a manifest, NOT append-only, no Timestamp; IDs are not
base62 — they are the project's own short alphanumeric deliverable IDs):
  deliverables -> deliverables.yaml  (<DeliverableID> -> Title, Path)
                                 Path is a quoted glob string or a block list of them.

And one mutable ADR-style LOG (NOT append-only; uses `LastUpdate`, not `Timestamp`):
  decisions -> decisions.yaml    (DecisionID -> AuthorAgent, Model, LastUpdate, Title,
                                 Description, Rationale, Scope, Impact, Reversibility,
                                 Implications, Alternatives, Remarks, ConfirmationType,
                                 Status, RelatedTo{Tasks,Decisions,Changes,Lessons,Events})
                                 RelatedTo sub-keys are optional BLOCK lists of IDs.

Each file is a YAML **list** whose items are single-key mappings: the entry ID is the
key, its fields are the nested mapping (this is what makes entries foldable in editors).

Design constraints (see tasks.md D5):
  * pyyaml-OPTIONAL: use PyYAML when importable; otherwise fall back to a targeted
    pure-Python (stdlib) parser for this constrained ledger format. Never shell out to
    another runtime — Python is the standardized deterministic tool for this project.

Usage:
    python3 validate_yaml_log.py <file> [kind]
    python3 validate_yaml_log.py .claude/workarea/changes.yaml
    python3 validate_yaml_log.py .claude/workarea/handoffs.yaml handoffs

If `kind` is omitted it is inferred from the filename. Exit 0 = valid, 1 = problems.
"""
import sys
import re
import os

# --------------------------------------------------------------------------- schema
BASE62 = r"[0-9A-Za-z]{8}"
TS = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

# 1.4.0 — every ledger entry is attributable to the session and operator that wrote it. Optional for
# entries that predate 1.4.0 (files are never rewritten); REQUIRED for new entries — the PostToolUse
# hook passes `--require-owner <ids>` for the IDs added by a write; `--require-owner all` for audits.
OWNER_FIELDS = {"OwnerSessionId", "OwnerSessionUserName"}

SCHEMAS = {
    "changes": {
        "id": re.compile(rf"^{BASE62}$"),
        "required": ["AuthorAgent", "Model", "Timestamp", "Layer", "Title",
                     "Description", "StateBefore", "StateAfter", "Remarks"],
    },
    "lessons": {
        "id": re.compile(rf"^{BASE62}$"),
        "required": ["AuthorAgent", "Model", "Timestamp", "Title",
                     "Description", "Remarks"],
    },
    "handoffs": {
        "id": re.compile(rf"^{BASE62}-(BEGIN|END)$"),
        "required": ["EventID", "TaskID", "AuthorAgent", "TargetAgent", "Timestamp",
                     "Title", "Description", "Scope", "Inputs", "Outputs"],
    },
    "events": {
        "id": re.compile(rf"^{BASE62}$"),
        "required": ["TaskID", "AuthorAgent", "Model", "Timestamp",
                     "EventType", "Title", "Remarks", "Status"],
        # 1.7.0: a DECISION event with DecisionID records a status transition of that decision
        # (decisions are append-only and partitioned per session; the latest such event is the
        # decision's effective Status).
        "optional": ["DecisionID"],
    },
    # Registry (manifest), not a ledger. IDs are the project's own short alphanumeric
    # deliverable IDs — constrained to what the pure-Python fallback tokenizer can
    # recognize as an entry key: alphanumeric only, no '.', '_', or '-'.
    "deliverables": {
        "id": re.compile(r"^[A-Za-z0-9]{1,32}$"),
        "required": ["Title", "Path"],
    },
    # ADR-style log. Since 1.7.0 append-only and partitioned per session: `Status` is the INITIAL
    # status; later transitions are `events` of EventType DECISION carrying `DecisionID`. Uses `LastUpdate` (not `Timestamp`) and a
    # Status lifecycle; enum fields and a `RelatedTo` mapping of block lists are checked in
    # `_validate_decision`. See `references/schemas.md § YAML-based Logs → Decision Log`.
    # `RelatedTo` is OPTIONAL — a foundational decision may stand alone; omit it entirely
    # rather than fabricate a cross-reference. When present it is shape-checked in
    # `_validate_decision`. All other fields are required.
    "decisions": {
        "id": re.compile(rf"^{BASE62}$"),
        "required": ["AuthorAgent", "Model", "LastUpdate", "Title", "Description",
                     "Rationale", "Scope", "Impact", "Reversibility", "Implications",
                     "Alternatives", "Remarks", "ConfirmationType", "Status"],
        "optional": ["RelatedTo"],
    },
}

EVENT_TYPES = {"TASK", "HANDOFF", "ISSUE", "CHANGE", "DECISION", "REVIEW", "AUDIT", "APPROVAL", "TEST"}
STATUS_BY_TYPE = {
    "TASK":     {"OPEN", "COMPLETED"},
    "HANDOFF":  {"BEGIN", "END"},
    "ISSUE":    {"OPEN", "CLOSED", "WORKAROUND", "NOT-FIXED"},
    "CHANGE":   {"OPEN", "COMPLETED"},
    "DECISION": {"OPEN", "ACCEPTED", "SUPERSEDED", "DEPRECATED"},
    "REVIEW":   {"OPEN", "PASS", "FAIL"},
    "AUDIT":    {"OPEN", "CONFORMANT", "NON-CONFORMANT"},
    "APPROVAL": {"OPEN", "GO", "NO-GO"},
    "TEST":     {"OPEN", "OK", "KO"},
}

# Change Log `Layer` vocabulary (mirrors the `<...>` choice set in the spec). Discriminates the
# scope of a change: CORE (AGENTS.md + Group-A tooling, hooks, harness config), ARCHETYPE (KS_PROJECT.md
# + Group-B skills + reusable engines), PROJECT (KS_SPEC.md + the deliverables + instance-specific data).
# 3.6.0 renamed METHOD → CORE (ADR 0016); METHOD stays readable in existing append-only ledgers.
CHANGE_LAYER = {"CORE", "ARCHETYPE", "PROJECT"}
CHANGE_LAYER_LEGACY = {"METHOD": "CORE"}     # 3.6.0: accepted on read (append-only ledgers keep old entries); write CORE

# Decision Log enum vocabularies (mirror the `<...>` choice sets in the spec).
DECISION_IMPACT = {"VERY LOW", "LOW", "MEDIUM", "HIGH", "VERY HIGH"}
DECISION_REVERSIBILITY = {"TRIVIAL", "EASY", "MEDIUM", "HARD", "VERY HARD"}
DECISION_CONFIRMATION = {"OPERATOR", "AUTO-MODE"}
IMPACT_ORDER = ["VERY LOW", "LOW", "MEDIUM", "HIGH", "VERY HIGH"]
REVERSIBILITY_ORDER = ["TRIVIAL", "EASY", "MEDIUM", "HARD", "VERY HARD"]
HIL_DEFAULT = {"impact": "HIGH", "reversibility": "HARD", "logic": "or", "mode": "enforce"}


def hil_policy(ledger_path=None):
    """[hil] from .agents/config.toml next to the workarea (2.1.0): the Human-in-the-Loop threshold.
    Defaults: Impact >= HIGH OR Reversibility >= HARD, enforce (2.3.0; was AND in 2.1–2.2). Bad values fall back per key."""
    pol = dict(HIL_DEFAULT)
    cands = []
    if ledger_path:
        ag = os.path.dirname(os.path.dirname(os.path.abspath(ledger_path)))
        cands += [os.path.join(ag, "config.toml"), os.path.join(ag, "config.toml")]
    root = os.environ.get("TKSFW_PROJECT_ROOT")
    if root:
        cands += [os.path.join(root, ".agents", "config.toml"), os.path.join(root, ".agents", "config.toml")]
    for mp in cands:
        if os.path.isfile(mp):
            try:
                import tomllib
                with open(mp, "rb") as fh:
                    t = tomllib.load(fh).get("hil") or {}
                if str(t.get("impact", "")).upper() in IMPACT_ORDER:
                    pol["impact"] = str(t["impact"]).upper()
                if str(t.get("reversibility", "")).upper() in REVERSIBILITY_ORDER:
                    pol["reversibility"] = str(t["reversibility"]).upper()
                if str(t.get("logic", "")).lower() in ("and", "or"):
                    pol["logic"] = str(t["logic"]).lower()
                if str(t.get("mode", "")).lower() in ("enforce", "advisory"):
                    pol["mode"] = str(t["mode"]).lower()
            except Exception:
                pass
            break
    return pol


def hil_required(fields, pol):
    """True when a decision is at or above the HIL threshold (operator confirmation required)."""
    try:
        hi = IMPACT_ORDER.index(str(fields.get("Impact"))) >= IMPACT_ORDER.index(pol["impact"])
        hr = REVERSIBILITY_ORDER.index(str(fields.get("Reversibility"))) >= REVERSIBILITY_ORDER.index(pol["reversibility"])
    except ValueError:
        return False
    return (hi and hr) if pol["logic"] == "and" else (hi or hr)


def hil_describe(pol):
    return f"Impact >= {pol['impact']} {pol['logic'].upper()} Reversibility >= {pol['reversibility']} ({pol['mode']})"


def hil_problems(fields, pol):
    """Violations of the HIL rule for one decision entry (AGENTS.md § Human in the Loop)."""
    out = []
    if not hil_required(fields, pol):
        return out
    thr = hil_describe(pol)
    if str(fields.get("ConfirmationType")) != "OPERATOR":
        out.append(f"HIL: Impact {fields.get('Impact')} / Reversibility {fields.get('Reversibility')} is at or above the threshold [{thr}] — ConfirmationType must be OPERATOR (ask the operator before it takes effect)")
    if str(fields.get("AuthorAgent", "main")) != "main" and str(fields.get("Status")) != "OPEN":
        out.append(f"HIL: above-threshold decision authored by `{fields.get('AuthorAgent')}` must stay OPEN — escalate; `main` asks the operator and logs the ACCEPTED transition (DECISION event)")
    return out
DECISION_STATUS = {"OPEN", "ACCEPTED", "SUPERSEDED", "DEPRECATED"}
RELATED_SUBKEYS = {"Tasks", "Decisions", "Changes", "Lessons", "Events"}

FILENAME_KIND = {
    "changes.yaml": "changes",
    "lessons.yaml": "lessons",
    "handoffs.yaml": "handoffs",
    "events.yaml": "events",
    "deliverables.yaml": "deliverables",
    "decisions.yaml": "decisions",
}


# --------------------------------------------------------------- pure-Python fallback
class ParseError(Exception):
    pass


def _fallback_parse(text):
    """Parse the constrained ledger subset without PyYAML.

    Supports exactly what `references/schemas.md` uses: a top-level list of single-key mappings,
    nested mappings, inline scalars (optionally quoted), `|-` literal block scalars,
    and simple `- item` string lists (for Inputs.Files / Outputs.Files). Indentation
    is spaces only (YAML forbids tabs); a tab in indentation is a hard error.

    Returns a list of (entry_id, field_dict) preserving order. Nested structures are
    returned as dicts/lists; scalars as strings. This is intentionally strict: anything
    outside the documented shape raises ParseError so validation fails loudly rather
    than silently mis-reading a malformed ledger.
    """
    lines = text.splitlines()

    # (indent, kind, key, value, raw_lineno) tokens; block scalars are pre-collapsed.
    tokens = []
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if stripped == "" or stripped.startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent] or (raw[:indent].strip("") != raw[:indent].replace("\t", "")):
            raise ParseError(f"line {i+1}: tab used in indentation (YAML requires spaces)")
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise ParseError(f"line {i+1}: tab used in indentation (YAML requires spaces)")

        body = raw[indent:]
        # list item?
        if body.startswith("- "):
            content = body[2:]
            # "- key: value" style
            m = re.match(r"^(-?[0-9A-Za-z]+(?:-[A-Z]+)?):\s*(.*)$", content)
            if m and _looks_like_key(content):
                tokens.append((indent, "listmap", m.group(1), m.group(2), i + 1))
            else:
                tokens.append((indent, "listitem", None, content, i + 1))
            i += 1
            continue
        if body == "-":
            tokens.append((indent, "listitem", None, "", i + 1))
            i += 1
            continue

        # key: value
        m = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", body)
        if not m:
            raise ParseError(f"line {i+1}: cannot parse {raw!r}")
        key, val = m.group(1), m.group(2)

        if val.strip() in ("|", "|-", "|+", ">", ">-", ">+"):
            # block scalar: gather deeper-indented lines
            block_lines = []
            j = i + 1
            base = None
            while j < n:
                bl = lines[j]
                if bl.strip() == "":
                    block_lines.append("")
                    j += 1
                    continue
                bindent = len(bl) - len(bl.lstrip(" "))
                if bindent <= indent:
                    break
                if base is None:
                    base = bindent
                block_lines.append(bl[base:])
                j += 1
            # trim trailing blank lines for chomped/clip; join literal with newlines
            while block_lines and block_lines[-1] == "":
                block_lines.pop()
            tokens.append((indent, "kv", key, "\n".join(block_lines), i + 1))
            i = j
            continue

        tokens.append((indent, "kv", key, val, i + 1))
        i += 1

    return _build(tokens)


def _looks_like_key(content):
    # Heuristic: an entry-id key like "7Kd2Rf9Q:" or "3pQ9mK2v-BEGIN:" starting a list map.
    return bool(re.match(r"^-?[0-9A-Za-z]+(?:-[A-Z]+)?:\s", content) or
                re.match(r"^-?[0-9A-Za-z]+(?:-[A-Z]+)?:$", content))


def _build(tokens):
    """Turn the flat indented token stream into the list-of-single-key-mappings."""
    entries = []
    idx = 0
    ntok = len(tokens)

    def parse_map(min_indent):
        nonlocal idx
        d = {}
        while idx < ntok:
            indent, kind, key, val, ln = tokens[idx]
            if indent < min_indent:
                break
            if kind == "kv":
                idx += 1
                if val == "" and idx < ntok and tokens[idx][0] > indent:
                    child_indent = tokens[idx][0]
                    if tokens[idx][1] == "listitem":
                        d[key] = parse_list(child_indent)
                    else:
                        d[key] = parse_map(child_indent)
                else:
                    d[key] = _scalar(val)
            else:
                break
        return d

    def parse_list(min_indent):
        nonlocal idx
        lst = []
        while idx < ntok:
            indent, kind, key, val, ln = tokens[idx]
            if indent < min_indent or kind not in ("listitem", "listmap"):
                break
            if kind == "listitem":
                idx += 1
                lst.append(_scalar(val))
            else:
                break
        return lst

    # top level: sequence of "- <id>:" list maps
    while idx < ntok:
        indent, kind, key, val, ln = tokens[idx]
        if kind != "listmap":
            raise ParseError(f"line {ln}: expected top-level '- <id>:' entry, got {kind}")
        idx += 1
        entry_id = key
        fields = {}
        if val.strip() != "":
            # inline "- id: something" is not how entries are shaped
            raise ParseError(f"line {ln}: entry id {entry_id!r} must head a nested mapping")
        # fields are indented deeper than the '- ' marker (indent+2)
        child_indent = indent + 2
        if idx < ntok and tokens[idx][0] >= child_indent:
            fields = parse_map(tokens[idx][0])
        entries.append((entry_id, fields))
    return entries


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


# ------------------------------------------------------------------------- load
def load_entries(path):
    """Return (entries, engine) where entries is a list of (id, field_dict).

    Uses PyYAML when available (authoritative full-YAML parse), else the pure-Python
    fallback. Both normalize to the same (id, fields) shape.
    """
    text = open(path, encoding="utf-8").read()
    try:
        import yaml  # noqa
        data = yaml.safe_load(text)
        if data is None:
            return [], "pyyaml"
        if not isinstance(data, list):
            raise ParseError("root is not a YAML list")
        out = []
        for item in data:
            if not isinstance(item, dict) or len(item) != 1:
                raise ParseError(f"entry is not a single-key mapping: {item!r}")
            (k, v), = item.items()
            out.append((str(k), v if isinstance(v, dict) else {}))
        return out, "pyyaml"
    except ImportError:
        return _fallback_parse(text), "stdlib-fallback"


# --------------------------------------------------------------------- validation
def validate(path, kind, require_owner=(), hil_ids=None):
    """`hil_ids`: decision IDs subject to the HIL rule as hard failures (new entries in a hook write);
    None → the rule is reported for every decision as warnings (see main). `advisory` mode never fails."""
    problems = []
    warnings = []
    pol = hil_policy(path) if kind == "decisions" else None
    try:
        entries, engine = load_entries(path)
    except ParseError as e:
        return [f"whole-file parse error: {e}"], "?"
    except Exception as e:  # pyyaml.YAMLError etc.
        return [f"whole-file YAML parse error: {e}"], "?"

    schema = SCHEMAS[kind]
    seen_ids = {}
    for pos, (eid, fields) in enumerate(entries, 1):
        tag = f"entry {pos} ({eid})"
        if not schema["id"].match(eid):
            problems.append(f"{tag}: bad ID for kind '{kind}'")
        seen_ids.setdefault(eid, []).append(pos)
        if not isinstance(fields, dict):
            problems.append(f"{tag}: fields are not a mapping")
            continue

        req = set(schema["required"])
        optional = set(schema.get("optional", ())) | OWNER_FIELDS
        if require_owner == "all" or eid in require_owner:
            req = req | OWNER_FIELDS                   # new entries (1.4.0+) must carry the owner fields
        present = set(fields)
        missing = req - present
        extra = present - req - optional
        if missing:
            problems.append(f"{tag}: missing {sorted(missing)}")
        if extra:
            problems.append(f"{tag}: unexpected {sorted(extra)}")

        if "OwnerSessionId" in fields and not re.fullmatch(BASE62, str(fields["OwnerSessionId"])):
            problems.append(f"{tag}: bad OwnerSessionId {fields['OwnerSessionId']!r} (base62, 8 chars — the session token)")
        if pol:
            hp = [f"{tag}: {m}" for m in hil_problems(fields, pol)]
            if hp:
                hard = hil_ids is not None and eid in hil_ids and pol["mode"] == "enforce"
                (problems if hard else warnings).extend(hp)
        if "OwnerSessionUserName" in fields and not str(fields["OwnerSessionUserName"]).strip():
            problems.append(f"{tag}: empty OwnerSessionUserName")
        if "Timestamp" in fields and not TS.fullmatch(str(fields["Timestamp"])):
            problems.append(f"{tag}: bad Timestamp {fields['Timestamp']!r}")
        if "Title" in fields and len(str(fields["Title"])) > 80:
            problems.append(f"{tag}: Title {len(str(fields['Title']))} chars > 80")

        if kind == "changes":
            _validate_change(tag, fields, problems)
        if kind == "events":
            _validate_event(tag, fields, problems)
        if kind == "handoffs":
            _validate_handoff(tag, eid, fields, problems)
        if kind == "deliverables":
            _validate_deliverable(tag, fields, problems)
        if kind == "decisions":
            _validate_decision(tag, fields, problems)

    for eid, positions in seen_ids.items():
        if len(positions) > 1 and not (kind == "handoffs"):
            problems.append(f"duplicate ID {eid} in entries {positions}")
    validate.warnings = warnings
    return problems, engine


def _validate_change(tag, fields, problems):
    """Change Log entry: enum-check the required `Layer` discriminator. Presence/absence is
    already enforced by the generic required-fields check; here we only validate the value.
    See `references/schemas.md § YAML-based Logs → Change Log`."""
    layer = fields.get("Layer")
    if layer is not None and str(layer) not in CHANGE_LAYER and str(layer) not in CHANGE_LAYER_LEGACY:
        problems.append(f"{tag}: Layer {layer!r} not in {sorted(CHANGE_LAYER)} (legacy METHOD is read as CORE)")


def _validate_event(tag, fields, problems):
    et = fields.get("EventType")
    if et is not None and et not in EVENT_TYPES:
        problems.append(f"{tag}: EventType {et!r} not in {sorted(EVENT_TYPES)}")
    did = fields.get("DecisionID")
    if did is not None:
        if not re.fullmatch(BASE62, str(did)):
            problems.append(f"{tag}: bad DecisionID {did!r} (base62, 8 chars)")
        if et != "DECISION":
            problems.append(f"{tag}: DecisionID only on EventType DECISION (got {et!r})")
    st = fields.get("Status")
    if et in STATUS_BY_TYPE and st is not None and str(st) not in STATUS_BY_TYPE[et]:
        problems.append(f"{tag}: Status {st!r} invalid for EventType {et} "
                        f"(allowed {sorted(STATUS_BY_TYPE[et])})")


def _validate_handoff(tag, eid, fields, problems):
    state = eid.rsplit("-", 1)[-1] if "-" in eid else None
    inp = fields.get("Inputs")
    if not isinstance(inp, dict) or "Files" not in inp:
        problems.append(f"{tag}: Inputs.Files missing")
    out = fields.get("Outputs")
    if not isinstance(out, dict):
        problems.append(f"{tag}: Outputs mapping missing")
        return
    for sub in ("Files", "Summary", "CandidateLessons"):
        if sub not in out:
            problems.append(f"{tag}: Outputs.{sub} missing")
    # BEGIN entries carry N/A placeholders; END entries carry real output.
    if state == "BEGIN":
        if str(out.get("CandidateLessons")) != "N/A":
            problems.append(f"{tag}: BEGIN Outputs.CandidateLessons must be \"N/A\"")
        if str(out.get("Summary")) != "N/A":
            problems.append(f"{tag}: BEGIN Outputs.Summary must be \"N/A\"")


def _validate_deliverable(tag, fields, problems):
    """Registry entry: Path is a non-empty glob string or a non-empty block list of them.
    Every glob must be relative (no leading '/'), contain no '..' segment, and not be a
    bare catch-all ('*'/'**') — those break glob expansion (dod_checks) and path
    relativization (Stop hook), or match everything.
    """
    path = fields.get("Path")
    if isinstance(path, str):
        items = [path]
    elif isinstance(path, list):
        if not path:
            problems.append(f"{tag}: Path list is empty")
        items = path
    else:
        problems.append(f"{tag}: Path must be a string or a block list of strings")
        return
    for p in items:
        if not isinstance(p, str) or not p.strip():
            problems.append(f"{tag}: Path entry must be a non-empty string")
            continue
        norm = p.replace("\\", "/")
        if norm.startswith("/"):
            problems.append(f"{tag}: Path {p!r} must be relative (no leading '/')")
        if ".." in norm.split("/"):
            problems.append(f"{tag}: Path {p!r} must not contain a '..' segment")
        if norm.strip("*/") == "":
            problems.append(f"{tag}: Path {p!r} is too broad (bare '*'/'**' catch-all)")


def _validate_decision(tag, fields, problems):
    """Mutable ADR entry: format-check `LastUpdate` (this log has no `Timestamp`), the four
    enum fields, and the `RelatedTo` mapping. `RelatedTo` sub-keys are all optional, but any
    present one must be a BLOCK list of ID strings — the pure-Python fallback parser does not
    read flow lists (`[a, b]`), so flow notation would silently mis-parse. Represent an empty
    relation by omitting its sub-key, not by an empty/inline list.
    """
    lu = fields.get("LastUpdate")
    if lu is not None and not TS.fullmatch(str(lu)):
        problems.append(f"{tag}: bad LastUpdate {lu!r} (want 'YYYY-MM-DD hh:mm:ss')")

    for key, allowed in (("Impact", DECISION_IMPACT),
                         ("Reversibility", DECISION_REVERSIBILITY),
                         ("ConfirmationType", DECISION_CONFIRMATION),
                         ("Status", DECISION_STATUS)):
        val = fields.get(key)
        if val is not None and str(val) not in allowed:
            problems.append(f"{tag}: {key} {val!r} not in {sorted(allowed)}")

    rel = fields.get("RelatedTo")
    if rel is None:
        return
    if not isinstance(rel, dict):
        problems.append(f"{tag}: RelatedTo must be a mapping of block lists "
                        f"(omit empty sub-keys; no flow lists)")
        return
    extra = set(rel) - RELATED_SUBKEYS
    if extra:
        problems.append(f"{tag}: RelatedTo has unexpected sub-keys {sorted(extra)} "
                        f"(allowed {sorted(RELATED_SUBKEYS)})")
    for sub, ids in rel.items():
        if sub not in RELATED_SUBKEYS:
            continue
        if not isinstance(ids, list) or not ids:
            problems.append(f"{tag}: RelatedTo.{sub} must be a non-empty block list "
                            f"(omit the sub-key if there is nothing to relate)")
            continue
        for ref in ids:
            if not isinstance(ref, str) or not ref.strip():
                problems.append(f"{tag}: RelatedTo.{sub} entry must be a non-empty ID string")


SHARD_RE = re.compile(r"^(changes|lessons|handoffs|events|decisions)\.([0-9A-Za-z]{8})\.yaml$")


def infer_kind(path):
    """Kind from the filename: `changes.yaml` (legacy / archive) or a session shard `changes.<token>.yaml`."""
    base = os.path.basename(path)
    m = SHARD_RE.match(base)
    if m:
        return m.group(1)
    return FILENAME_KIND.get(base)


def main():
    argv = sys.argv[1:]
    require_owner = ()
    if "--require-owner" in argv:
        i = argv.index("--require-owner")
        val = argv[i + 1] if i + 1 < len(argv) else "all"
        require_owner = "all" if val == "all" else set(x for x in val.split(",") if x)
        del argv[i:i + 2]
    hil_ids = None
    if "--hil-ids" in argv:
        i = argv.index("--hil-ids")
        val = argv[i + 1] if i + 1 < len(argv) else ""
        hil_ids = set(x for x in val.split(",") if x)
        del argv[i:i + 2]
    if not argv:
        print("usage: validate_yaml_log.py <file> [changes|lessons|handoffs|events|deliverables|decisions] [--require-owner all|ID,ID] [--hil-ids ID,ID]")
        sys.exit(2)
    path = argv[0]
    kind = argv[1] if len(argv) > 1 else infer_kind(path)
    if kind not in SCHEMAS:
        print(f"FAIL: cannot determine ledger kind for {path!r} "
              f"(pass one of {sorted(SCHEMAS)})")
        sys.exit(2)
    if not os.path.exists(path):
        print(f"FAIL: {path} not found")
        sys.exit(1)

    problems, engine = validate(path, kind, require_owner, hil_ids)
    for w in getattr(validate, "warnings", []):
        print(f"WARN ({path}): {w}")
    if problems:
        print(f"FAIL ({path}, kind='{kind}', parser={engine}):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    # count entries for the OK line
    entries, _ = load_entries(path)
    print(f"OK: {path} valid — {len(entries)} entries, kind '{kind}' conforms (parser={engine})")
    legacy = [eid for eid, f in entries if isinstance(f, dict) and not OWNER_FIELDS <= set(f)]
    if legacy:
        print(f"WARN: {len(legacy)} entr{'y' if len(legacy) == 1 else 'ies'} without OwnerSessionId/OwnerSessionUserName "
              f"(pre-1.4.0; accepted, never rewritten)")
    sys.exit(0)


if __name__ == "__main__":
    main()
