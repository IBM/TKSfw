#!/usr/bin/env python3
"""Shared, harness-neutral helpers for the project hooks (Codex CLI and Claude Code).

Design goals
  * ZERO harness-specific payload dependencies for edit detection: edits are detected by
    hashing the watched files around each tool call (see `snapshot()` / `diff()`), never
    from `tool_input.file_path` (Claude-only) or the transcript (unstable in both).
  * The few payload fields that ARE used exist in both harnesses under the same names
    (`session_id`, `cwd`, `hook_event_name`, `tool_name`, `tool_use_id`, `stop_hook_active`,
    `source`). The only divergent field — the turn key — is normalized by `turn_key()`
    (`turn_id` in Codex, `prompt_id` in Claude Code).
  * Fail-open everywhere: a hook that hits an internal error exits 0 silently. It must never
    wedge a turn. Errors go to `.agents/workarea/.hook-state/hooks.log`.
  * Standard library only. No `__pycache__` is left in the repo.

Layout (all relative to the project root):
  .agents/hooks/                 these scripts (in-project layout) — or <plugin>/hooks/ when the
                                 framework is installed as a Codex / Claude Code plugin
  .agents/workarea/              tasks.md + the YAML ledgers + deliverables.yaml + STATE.md
  .agents/workarea/.hook-state/  hashes.json, journal.jsonl, hooks.log (runtime bookkeeping,
                                 excluded from hashing and from every ledger rule)
  .agents/skills/yaml-log-entry/assets/  shared pyyaml-optional ledger parser (load_entries)
                                 — or <plugin>/skills/yaml-log-entry/assets/ in plugin mode
  .agents/agents/<name>.toml     agent definitions (source); .codex/agents/ and .claude/agents/ are
                                 generated mirrors (agentlib.py) and never watched

Project-root resolution (`resolve_project_root()`), first match wins:
  1. $TKSFW_PROJECT_ROOT                explicit override (tests, unusual layouts)
  2. $CLAUDE_PROJECT_DIR                exported by Claude Code to hook processes
  3. walk up from the current directory until a directory containing AGENTS.md or
     .agents/workarea is found (both harnesses run hooks with cwd = project directory)
  4. two levels above this file, when the scripts live at <root>/.agents/hooks/ (legacy)
The workarea and STATE.md therefore always stay inside the project, never in the plugin
cache directory (which is ephemeral and replaced on plugin updates).
"""
import sys
sys.dont_write_bytecode = True
import os
import io
import json
import glob
import time
import hashlib
import fnmatch
import re
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_MARKERS = ("AGENTS.md", os.path.join(".agents", "workarea"))


def _looks_like_project(path):
    return any(os.path.exists(os.path.join(path, m)) for m in ROOT_MARKERS)


def resolve_project_root():
    """See the module docstring. Returns (absolute normalized path, how) where how is one of
    env | marker | legacy | cwd — `cwd` means NO project was found (the guard treats it as unarmed)."""
    for var in ("TKSFW_PROJECT_ROOT", "CLAUDE_PROJECT_DIR"):
        p = os.environ.get(var)
        if p and os.path.isdir(p):
            return os.path.normpath(os.path.abspath(p)), "env"
    cur = os.path.abspath(os.getcwd())
    while True:
        if _looks_like_project(cur):
            return cur, "marker"
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    legacy = os.path.normpath(os.path.join(HERE, "..", ".."))          # .agents/hooks -> root
    if os.path.basename(os.path.dirname(HERE)) == ".agents":
        return legacy, "legacy"
    return os.path.abspath(os.getcwd()), "cwd"                           # last resort: cwd


def resolve_validator_dir(project_root):
    """`yaml-log-entry/assets` next to these scripts (plugin layout: <plugin>/hooks + <plugin>/skills,
    or in-project: .agents/hooks + .agents/skills) — falling back to the project copy."""
    candidates = (
        os.path.join(os.path.dirname(HERE), "skills", "yaml-log-entry", "assets"),
        os.path.join(project_root, ".agents", "skills", "yaml-log-entry", "assets"),
    )
    for c in candidates:
        if os.path.isfile(os.path.join(c, "validate_yaml_log.py")):
            return c
    return candidates[-1]


PROJECT_ROOT, ROOT_HOW = resolve_project_root()
WORKAREA_REL = ".agents/workarea"
WORKAREA = os.path.join(PROJECT_ROOT, ".agents", "workarea")
STATE_DIR = os.path.join(WORKAREA, ".hook-state")
HASHES = os.path.join(STATE_DIR, "hashes.json")
JOURNAL = os.path.join(STATE_DIR, "journal.jsonl")
LOG = os.path.join(STATE_DIR, "hooks.log")
LOCK = os.path.join(STATE_DIR, ".lock")
VALIDATOR_DIR = resolve_validator_dir(PROJECT_ROOT)
VALIDATOR = os.path.join(VALIDATOR_DIR, "validate_yaml_log.py")
SCHEMAS_MD = os.path.normpath(os.path.join(VALIDATOR_DIR, "..", "references", "schemas.md"))
PLUGIN_MODE = os.path.basename(os.path.dirname(HERE)) != ".agents"    # scripts run from a plugin
PLUGIN_ROOT = os.path.dirname(HERE) if PLUGIN_MODE else None
MANIFEST = os.path.join(PROJECT_ROOT, ".agents", ".tksfw.json")        # written by new_project.py / tksfw-init
PROJECT_HOOKS = os.path.join(PROJECT_ROOT, ".agents", "hooks", "hooks.json")
REGISTRY = os.path.join(WORKAREA, "deliverables.yaml")
MODELS_TOML = os.path.join(PROJECT_ROOT, ".agents", "models.toml")   # model routing table (route_model.py)
AGENT_VALIDATOR = os.path.join(os.path.dirname(VALIDATOR_DIR), "..", "define-agent", "assets", "validate_agent.py")
AGENT_VALIDATOR = os.path.normpath(AGENT_VALIDATOR)                  # sibling skill: plugin or in-project layout
AGENTS_SRC = os.path.join(PROJECT_ROOT, ".agents", "agents")           # neutral agent definitions
AGENT_FILE_RE = re.compile(r"^\.agents/agents/[^/]+\.toml$")
MIRROR_PREFIXES = (".claude/skills/", ".codex/agents/", ".claude/agents/")   # generated, never watched
STATE_MD = os.path.join(WORKAREA, "STATE.md")

LEDGER_FILES = ("changes.yaml", "lessons.yaml", "handoffs.yaml", "events.yaml",
                "decisions.yaml", "deliverables.yaml")
PLAN_FILES = ("tasks.md", "tasks-archive.md")
# Files whose edit is a loggable METHOD/ARCHETYPE change (Layer table in AGENTS.md).
ROOT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "MISSION.md",
                          "Job Role Definitions.md")
FRAMEWORK_DIRS = (".agents", ".codex", ".claude")           # minus the workarea, see classify()
# Tool names that mean "a subagent was delegated to" (Claude: Agent (formerly Task);
# Codex: spawn_agent, which its matcher also exposes as Agent).
DELEGATION_TOOLS = {"Agent", "Task", "spawn_agent"}
IGNORED_PARTS = {"__pycache__", ".DS_Store", ".hook-state", ".git", "node_modules"}


# ----------------------------------------------------------------------------- arming
def read_manifest():
    """`.agents/.tksfw.json` as a dict, or None when absent/unreadable."""
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        return m if isinstance(m, dict) else None
    except Exception:
        return None


def armed():
    """(bool, reason). The framework acts in a project only when it is ARMED:
         1. `.agents/.tksfw.json` exists and its `enabled` is not false          → armed
            (`"enabled": false` disarms the project for both harnesses — the per-project off switch
             Codex lacks natively; Claude Code users may additionally use enabledPlugins)
         2. no manifest, scripts run IN-PROJECT (.agents/hooks) and the root was found by marker →
            armed for compatibility with projects created before the manifest existed
         3. anything else (user-level plugin in a folder without a manifest, cwd fallback)   → not armed
       Plugin instance in a project that carries its own .agents/hooks/hooks.json → YIELDS (the project
       pins its framework version; running both layers would journal everything twice)."""
    if ROOT_HOW == "cwd":
        return False, "no project found (no AGENTS.md / .agents/workarea above cwd)"
    if PLUGIN_MODE and os.path.isfile(PROJECT_HOOKS):
        return False, "yield: project carries its own .agents/hooks (in-project layout wins)"
    m = read_manifest()
    if m is not None:
        if m.get("enabled") is False:
            return False, "disabled in .agents/.tksfw.json"
        return True, "manifest"
    if not PLUGIN_MODE and ROOT_HOW in ("marker", "legacy", "env"):
        return True, "in-project layout without manifest (legacy)"
    return False, "no .agents/.tksfw.json (project not initialised for TKSfw)"


def guard():
    """Call FIRST in every hook, before any file is touched: exit 0 silently when not armed.
    Nothing is logged (a log would create .hook-state in a folder that is not a project)."""
    ok, _reason = armed()
    if not ok:
        sys.exit(0)


def plugin_version():
    if not PLUGIN_ROOT:
        return None
    for sub in (".codex-plugin", ".claude-plugin"):
        try:
            with open(os.path.join(PLUGIN_ROOT, sub, "plugin.json"), encoding="utf-8") as fh:
                v = json.load(fh).get("version")
            if isinstance(v, str):
                return v
        except Exception:
            continue
    return None


def version_skew():
    """One-line warning when the project manifest and the plugin differ in major.minor, else ''."""
    m = read_manifest() or {}
    pv, mv = plugin_version(), m.get("version")
    if not pv or not isinstance(mv, str):
        return ""
    if pv.split(".")[:2] != mv.split(".")[:2]:
        return (f"TKSfw version skew: project instance {mv}, installed plugin {pv} — run the tksfw-init "
                f"skill with --update (or tools/new_project.py --update) to refresh the method files.")
    return ""


# ----------------------------------------------------------------------------- payload
def read_payload():
    """Hook JSON from stdin; {} when absent/unparseable (standalone runs)."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def harness(payload):
    """'codex' | 'claude' | 'unknown' — informational only (journaled), never branched on
    for detection logic."""
    if "turn_id" in payload or "model" in payload:
        return "codex"
    if "prompt_id" in payload or "effort" in payload:
        return "claude"
    return "unknown"


def turn_key(payload):
    """Turn identity: Codex `turn_id`, Claude Code `prompt_id`; both are stable across all
    hooks of the same turn. Falls back to the session id (whole session = one 'turn')."""
    return (payload.get("turn_id") or payload.get("prompt_id")
            or payload.get("session_id") or "unknown")


def emit(obj):
    """Print one JSON object on stdout (the only stdout shape both harnesses accept on
    every event)."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def additional_context(event_name, text):
    return {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}


# ----------------------------------------------------------------------------- state io
def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def log(msg):
    try:
        ensure_state_dir()
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


@contextmanager
def locked():
    """Serialize hook instances: both harnesses run matching hooks in parallel, and Claude Code
    runs PostToolUse concurrently for parallel tool calls. Advisory flock; no-op where fcntl is
    unavailable (Windows)."""
    ensure_state_dir()
    fh = open(LOCK, "a+")
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        fh.close()


def atomic_write(path, text):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def append_journal(entry):
    ensure_state_dir()
    with open(JOURNAL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_journal():
    out = []
    try:
        with open(JOURNAL, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return out


# ----------------------------------------------------------------------------- ledgers
def load_entries(path):
    """(id, fields) entries via the skill's shared pyyaml-optional parser; [] on any problem."""
    try:
        if not os.path.exists(path):
            return []
        if VALIDATOR_DIR not in sys.path:
            sys.path.insert(0, VALIDATOR_DIR)
        from validate_yaml_log import load_entries as _load
        entries, _ = _load(path)
        return entries
    except Exception:
        return []


def deliverable_globs():
    """Path globs from deliverables.yaml (the only source of 'what is a deliverable')."""
    globs = []
    for _id, fields in load_entries(REGISTRY):
        if not isinstance(fields, dict):
            continue
        p = fields.get("Path")
        if isinstance(p, str):
            globs.append(p)
        elif isinstance(p, list):
            globs.extend(x for x in p if isinstance(x, str))
    out = []
    for g in globs:
        g = g.replace("\\", "/")
        if g.startswith("./"):
            g = g[2:]
        if g:
            out.append(g)
    return out


# ----------------------------------------------------------------------------- watching
def _ignored(rel):
    parts = rel.split("/")
    return any(p in IGNORED_PARTS for p in parts) or rel.endswith(".DS_Store")


def _rel(path):
    return os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")


def classify(rel, globs=None):
    """Category of a project-relative path, or None when it is not watched.
       ledger:<name>  one of the six workarea YAML files (name without .yaml)
       plan           tasks.md / tasks-archive.md (bookkeeping, never loggable)
       framework      .agents/** .codex/** .claude/** (minus workarea) + root instruction files
       deliverable    matches a deliverables.yaml glob
    STATE.md and .hook-state/** are never watched (generated / runtime)."""
    if _ignored(rel):
        return None
    if rel.startswith(WORKAREA_REL + "/"):
        base = rel[len(WORKAREA_REL) + 1:]
        if "/" in base:
            return None                       # agent work areas: not tracked
        if base in LEDGER_FILES:
            return "ledger:" + base[:-5]
        if base in PLAN_FILES:
            return "plan"
        return None                           # STATE.md, scratch
    if rel.startswith(MIRROR_PREFIXES):
        return None                           # generated mirrors (skills, agent definitions), not sources
    top = rel.split("/", 1)[0]
    if top in FRAMEWORK_DIRS:
        return "framework"
    if "/" not in rel and rel in ROOT_INSTRUCTION_FILES:
        return "framework"
    if globs is None:
        globs = deliverable_globs()
    for g in globs:
        if fnmatch.fnmatch(rel, g) or glob_match_tail(rel, g):
            return "deliverable"
    return None


def glob_match_tail(rel, g):
    """Match the last N path segments of `rel` against an N-segment glob (belt and braces for
    deliverables registered by a sub-path)."""
    gs = g.split("/")
    rs = rel.split("/")
    return len(rs) >= len(gs) and fnmatch.fnmatch("/".join(rs[-len(gs):]), g)


def _walk(top_rel):
    top = os.path.join(PROJECT_ROOT, top_rel)
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_PARTS]
        for f in filenames:
            yield _rel(os.path.join(dirpath, f))


def watched_files():
    """Set of project-relative paths currently under watch."""
    globs = deliverable_globs()
    files = set()
    # workarea ledgers + plan
    for name in LEDGER_FILES + PLAN_FILES:
        p = os.path.join(WORKAREA, name)
        if os.path.isfile(p):
            files.add(_rel(p))
    # framework
    for d in FRAMEWORK_DIRS:
        if os.path.isdir(os.path.join(PROJECT_ROOT, d)):
            for rel in _walk(d):
                if rel.startswith(WORKAREA_REL + "/") or rel.startswith(MIRROR_PREFIXES):
                    continue                          # generated mirrors (sync_harness / agentlib)
                if not _ignored(rel):
                    files.add(rel)
    for f in ROOT_INSTRUCTION_FILES:
        if os.path.isfile(os.path.join(PROJECT_ROOT, f)):
            files.add(f)
    # deliverables (registry globs, relative to the project root; ** is recursive)
    for g in globs:
        if g in ("*", "**") or g.startswith("/") or ".." in g.split("/"):
            continue
        for m in glob.glob(os.path.join(PROJECT_ROOT, g), recursive=True):
            if os.path.isfile(m):
                rel = _rel(m)
                if not _ignored(rel):
                    files.add(rel)
    return files, globs


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot():
    """{rel_path: sha256} for every watched file that exists. Content hashes — never mtimes —
    because the workspace is a cloud-synced (Box) folder whose mtimes are perturbed by sync."""
    files, globs = watched_files()
    snap = {}
    for rel in sorted(files):
        try:
            snap[rel] = sha256_file(os.path.join(PROJECT_ROOT, rel))
        except Exception:
            continue
    return snap, globs


def diff(before, after, globs):
    """List of {path, kind, class} for added/modified/deleted watched files."""
    changed = []
    for rel in sorted(set(before) | set(after)):
        b, a = before.get(rel), after.get(rel)
        if b == a:
            continue
        kind = "added" if b is None else ("deleted" if a is None else "modified")
        cls = classify(rel, globs)
        if cls is None:
            continue
        changed.append({"path": rel, "kind": kind, "class": cls})
    return changed


def record_changes(payload, phase, tool_name=None, tool_use_id=None):
    """Hash the watched set, compare to the stored baseline, journal the delta, store the new
    baseline. Returns (changed, first_run). Must be called under `locked()`."""
    before = load_json(HASHES, None)
    after, globs = snapshot()
    first_run = before is None
    changed = [] if first_run else diff(before, after, globs)
    delegation = bool(tool_name and tool_name in DELEGATION_TOOLS)
    if changed or delegation:
        append_journal({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "harness": harness(payload),
            "session_id": payload.get("session_id"),
            "turn": turn_key(payload),
            "phase": phase,                       # tool | prompt | session
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "delegation": delegation,
            "changed": changed,
        })
    if first_run or changed:
        atomic_write(HASHES, json.dumps(after, indent=0, sort_keys=True))
    return changed, first_run


# ----------------------------------------------------------------------------- analysis
def entries_for_turn(entries, payload):
    """Journal entries of the current turn. Primary key: the normalized turn key; fallback when
    a harness omits it: same session, after the last `stop` marker."""
    turn = turn_key(payload)
    sid = payload.get("session_id")
    same_turn = [e for e in entries if e.get("turn") == turn and e.get("type") != "stop"]
    if turn != sid and turn != "unknown":
        return same_turn
    out = []
    for e in entries:
        if e.get("session_id") != sid:
            continue
        if e.get("type") == "stop":
            out = []
            continue
        out.append(e)
    return out


def unlogged(entries):
    """Order-based, deterministic completeness check over journal entries (agent phases only):
      deliverable  edit to a registry-matched deliverable AFTER the last changes.yaml write
      framework    edit to .agents/.codex/.claude/** or a root instruction file AFTER the last
                   changes.yaml write
      handoff      a delegation AFTER the last handoffs.yaml OR events.yaml write
    Returns (flags dict, paths dict) where paths lists the offending files."""
    last = {"deliverable": -1, "framework": -1, "delegation": -1,
            "changes": -1, "handoffs": -1, "events": -1}
    paths = {"deliverable": [], "framework": []}
    i = 0
    for e in entries:
        if e.get("phase") not in (None, "tool"):
            continue                              # external edits are not the agent's to log
        i += 1
        if e.get("delegation"):
            last["delegation"] = i
        for c in e.get("changed", []):
            cls = c.get("class") or ""
            if cls == "ledger:changes":
                last["changes"] = i
                paths["deliverable"].clear(); paths["framework"].clear()
            elif cls == "ledger:handoffs":
                last["handoffs"] = i
            elif cls == "ledger:events":
                last["events"] = i
            elif cls in ("deliverable", "framework"):
                last[cls] = i
                if c["path"] not in paths[cls]:
                    paths[cls].append(c["path"])
    flags = {
        "deliverable": last["deliverable"] >= 0 and last["deliverable"] > last["changes"],
        "framework": last["framework"] >= 0 and last["framework"] > last["changes"],
        "handoff": last["delegation"] >= 0 and (last["delegation"] > last["handoffs"]
                                                or last["delegation"] > last["events"]),
    }
    return flags, paths
