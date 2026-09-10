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
import socket
HOOK_STATE = os.path.join(WORKAREA, ".hook-state")
HOSTNAME = re.sub(r"[^A-Za-z0-9._-]", "_", os.environ.get("TKSFW_HOST") or socket.gethostname().split(".")[0] or "host")
# 1.7.0 — mutable per-machine state lives under hosts/<hostname>/ so a cloud-synced project folder (Box,
# Dropbox, OneDrive) never has two machines writing the same journal/snapshot/lock file. Only sessions/
# is shared: each record is written by exactly one machine, and sharing them makes "another session is
# active" visible across machines.
STATE_DIR = os.path.join(HOOK_STATE, "hosts", HOSTNAME)
HASHES = os.path.join(STATE_DIR, "hashes.json")          # legacy single snapshot (pre-1.4.0); unused
SESSIONS_DIR = os.path.join(HOOK_STATE, "sessions")       # <token>.json per harness session (1.4.0) — shared
ID_INDEX = os.path.join(STATE_DIR, "ids.json")            # {rel: {hash, ids→owner}} as last seen by any hook on this host
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
def _config_toml():
    """`.agents/config.toml` (3.0.0) — or the legacy `.agents/models.toml` when only that exists."""
    new = os.path.join(PROJECT_ROOT, ".agents", "config.toml")
    old = os.path.join(PROJECT_ROOT, ".agents", "models.toml")
    return old if (not os.path.isfile(new) and os.path.isfile(old)) else new


CONFIG_TOML = _config_toml()                                          # project configuration (routing, hil, state, delegation)
CONFIG_TOML_REL = os.path.relpath(CONFIG_TOML, PROJECT_ROOT).replace(os.sep, "/")
MODELS_TOML, MODELS_TOML_REL = CONFIG_TOML, CONFIG_TOML_REL           # legacy names kept for callers
AGENT_VALIDATOR = os.path.join(os.path.dirname(VALIDATOR_DIR), "..", "define-agent", "assets", "validate_agent.py")
AGENT_VALIDATOR = os.path.normpath(AGENT_VALIDATOR)                  # sibling skill: plugin or in-project layout
AGENTS_SRC = os.path.join(PROJECT_ROOT, ".agents", "agents")           # neutral agent definitions
AGENT_FILE_RE = re.compile(r"^\.agents/agents/[^/]+\.toml$")
MIRROR_PREFIXES = (".claude/skills/", ".codex/agents/", ".claude/agents/",   # generated, never watched
                   ".agents/worktrees/",                                       # subagent worktrees (delegate-work)
                   ".agents/history/")                                         # previous generations (ks project reset --archive)
STATE_MD = os.path.join(WORKAREA, "STATE.md")

LEDGER_FILES = ("changes.yaml", "lessons.yaml", "handoffs.yaml", "events.yaml",
                "decisions.yaml", "deliverables.yaml")
# 1.7.0 — ledgers are PARTITIONED BY SESSION: a session writes only `<ledger>.<token>.yaml` (its shard);
# every other shard is read-only for it; unsuffixed `<ledger>.yaml` is the read-only legacy shard.
# deliverables.yaml (registry) and tasks.md (plan) stay single by nature.
SHARDED = ("changes", "lessons", "handoffs", "events", "decisions")
SHARD_RE = re.compile(r"^(changes|lessons|handoffs|events|decisions)\.([0-9A-Za-z]{8})\.yaml$")
LEDGER_LIKE_RE = re.compile(r"^(changes|lessons|handoffs|events|decisions|deliverables|tasks)[ .(_-].*")
PLAN_FILES = ("tasks.md", "tasks-archive.md")
ARCHIVE_REL = "archive"                                             # .agents/workarea/archive/<ledger>.yaml, archive/tasks.md
ARCHIVE_LEDGERS = ("changes.yaml", "lessons.yaml", "handoffs.yaml", "events.yaml", "decisions.yaml")
APPEND_ONLY_LEDGERS = ("changes", "lessons", "handoffs", "events", "decisions")   # 1.7.0: decisions append-only too
MUTABLE_LEDGERS = ("deliverables",)                                   # registry: own entries may be rewritten
SESSION_ACTIVE_SEC = 30 * 60                                          # heartbeat window for "another session is active"
SESSION_EXPIRE_SEC = 24 * 3600                                        # snapshot/session files older than this are pruned
# Files whose edit is a loggable METHOD/ARCHETYPE change (Layer table in AGENTS.md).
ROOT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "MISSION.md",
                          "Job Role Definitions.md")
FRAMEWORK_DIRS = (".agents", ".codex", ".claude")           # minus the workarea, see classify()
# 2.2.0 — project layers: L3 archetype (Layer: ARCHETYPE) and L4 project spec (Layer: PROJECT) are watched
# INPUTS (class `layer:l3` / `layer:l4`), never deliverables. Convention at the project root; a `layers`
# stanza in the manifest declares other paths. Resolution, status and the injected block: layers.py.
LAYER_CONVENTION = {"l3": "KS_PROJECT.md", "l4": "KS_SPEC.md"}
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


def layer_paths():
    """{'l3': rel, 'l4': rel} — declared in the manifest `layers` stanza (relative, inside the root,
    .md) or the convention. Declared-but-absent files are included so their appearance is journaled."""
    m = read_manifest() or {}
    lay = m.get("layers") if isinstance(m.get("layers"), dict) else {}
    out = {}
    for k, conv in LAYER_CONVENTION.items():
        raw = lay.get(k)
        rel = None
        if isinstance(raw, str) and raw.strip():
            p = raw.strip().replace("\\", "/")
            p = p[2:] if p.startswith("./") else p
            if not p.startswith("/") and not re.match(r"^[A-Za-z]:/", p) and ".." not in p.split("/") and p.lower().endswith(".md"):
                rel = p
        out[k] = rel or conv
    return out


def layer_class(rel):
    """'layer:l3' | 'layer:l4' when `rel` is a resolved layer file (config or convention), else None."""
    for k, p in layer_paths().items():
        if rel == p:
            return "layer:" + k
    return None


def guard():
    """Call FIRST in every hook, before any file is touched: exit 0 silently when not armed.
    Nothing is logged (a log would create .hook-state in a folder that is not a project)."""
    ok, _reason = armed()
    if not ok:
        sys.exit(0)


def install_line():
    """'TKSfw v<ver> installed|updated <ts> (<mode>) by <op> — not yet in changes.yaml: log it …' or ''.
    The manifest's `installs` log (new_project.py) is compared with the METHOD-layer changes entries:
    once an entry with Timestamp >= the install stamp exists, the line disappears (2.5.0)."""
    m = read_manifest() or {}
    inst = m.get("installs") or []
    if not inst:
        return ""
    last = inst[-1]
    ts = str(last.get("ts") or "")
    try:
        for _i, f in load_kind("changes"):
            if str(f.get("Layer", "")).upper() == "METHOD" and str(f.get("Timestamp", "")) >= ts:
                return ""
    except Exception as e:
        log(f"install_line: {e}")
    verb = "installed" if last.get("action") == "init" else "updated to"
    who = f" by {last['operator']}" if last.get("operator") else ""
    return (f"TKSfw {verb} v{last.get('version', '?')} on {ts[:16]} ({last.get('mode', '?')} mode){who} — not yet recorded: "
            f"log it now in changes.yaml (Layer METHOD, Title \"TKSfw v{last.get('version', '?')} {verb.split()[0]}\"); "
            "the operator was told this happens automatically.")


def generation_line():
    """'Generation N — reset <ts> by <op> (<mode>); previous generation in <history>' or ''."""
    m = read_manifest() or {}
    resets = m.get("resets") or []
    if not resets:
        return ""
    last = resets[-1]
    where = f"; previous generation in `{last['history']}`" if last.get("history") else "; previous ledgers were cleared"
    return (f"Generation {len(resets) + 1} — reset {last.get('ts', '?')} by {last.get('operator') or '?'} "
            f"({last.get('mode', 'clear')}){where}. Empty ledgers are expected; start the plan afresh.")


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


# ----------------------------------------------------------------------------- sessions (1.4.0)
_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def mint_token(n=8):
    import secrets
    return "".join(secrets.choice(_B62) for _ in range(n))


def _session_files():
    try:
        return [os.path.join(SESSIONS_DIR, f) for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
    except FileNotFoundError:
        return []


def list_sessions():
    out = []
    for f in _session_files():
        d = load_json(f, None)
        if isinstance(d, dict) and d.get("token"):
            out.append(d)
    return out


def session_record(payload):
    """The session record for this harness session_id, or None."""
    sid = payload.get("session_id")
    if not sid:
        return None
    for d in list_sessions():
        if d.get("harness_session_id") == sid:
            return d
    return None


def session_token(payload, create=False):
    """Framework session token (base62-8) for the harness session in `payload`. With create=True a
    missing record is minted (SessionStart does this; any hook may as a fallback). Returns "" when
    unknown and not created (e.g. payload without session_id)."""
    rec = session_record(payload)
    if rec:
        return rec["token"]
    if not create or not payload.get("session_id"):
        return ""
    existing = {d["token"] for d in list_sessions()}
    tok = mint_token()
    while tok in existing:
        tok = mint_token()
    ensure_state_dir()
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    rec = {"token": tok, "harness_session_id": payload["session_id"], "harness": harness(payload),
           "operator": operator() or "", "host": HOSTNAME, "started": time.time(), "last_seen": time.time()}
    atomic_write(os.path.join(SESSIONS_DIR, tok + ".json"), json.dumps(rec, indent=1))
    export_session_env(tok)
    return tok


def export_session_env(tok):
    """Claude Code hands SessionStart hooks $CLAUDE_ENV_FILE — variables appended there reach every later
    Bash-tool command of the session. Export the token so `ks … --session` (no id) resolves exactly (3.4.0).
    Codex has no equivalent; the model passes its token from the SessionStart block."""
    path = os.environ.get("CLAUDE_ENV_FILE")
    if not path or not tok:
        return
    try:
        cur = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
        if f"TKSFW_SESSION={tok}" not in cur:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"\nexport TKSFW_SESSION={tok}\n")
    except Exception as e:
        log(f"export_session_env: {e}")


def session_routing(payload):
    """Session-scoped routing override (`ks routing use <table> --session`): the `routing` key of this
    session's record, or None (3.4.0)."""
    rec = session_record(payload)
    return (rec or {}).get("routing") or None


def touch_session(payload):
    """Heartbeat: update last_seen of this session's record (no-op when unknown)."""
    rec = session_record(payload)
    if not rec:
        return
    rec["last_seen"] = time.time()
    rec.setdefault("host", HOSTNAME)
    export_session_env(rec["token"])                      # resume / compaction: the env file may be fresh
    try:
        atomic_write(os.path.join(SESSIONS_DIR, rec["token"] + ".json"), json.dumps(rec, indent=1))
    except Exception:
        pass


def other_active_sessions(payload, within=SESSION_ACTIVE_SEC):
    """Other sessions whose heartbeat is within `within` seconds."""
    me = session_token(payload)
    now = time.time()
    return [d for d in list_sessions() if d["token"] != me and now - float(d.get("last_seen", 0)) <= within]


def prune_sessions(expire=SESSION_EXPIRE_SEC):
    """Remove session records and per-session snapshots not seen for `expire` seconds."""
    now = time.time()
    for d in list_sessions():
        if now - float(d.get("last_seen", 0)) > expire:
            for f in (os.path.join(SESSIONS_DIR, d["token"] + ".json"), hashes_path(d["token"]), session_ids_path(d["token"])):
                try:
                    os.remove(f)
                except OSError:
                    pass


USER_CONFIG = os.path.join(os.environ.get("TKSFW_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "tksfw"), "user.toml")


def operator_source():
    """(name, source) — source ∈ env | file | git | "". The canonical configuration item is
    ~/.config/tksfw/user.toml (`schema = 1`, `name = "…"`), written by `new_project.py --set-operator`;
    TKSFW_USER overrides it (CI, one-off shells); git config user.name is a fallback and is reported
    as such so the operator knows the item is not set."""
    v = os.environ.get("TKSFW_USER", "").strip()
    if v:
        return v, "env"
    try:
        for line in open(USER_CONFIG, encoding="utf-8"):
            m = re.match(r'^\s*name\s*=\s*"([^"]*)"\s*(#.*)?$', line)
            if m and m.group(1).strip():
                return m.group(1).strip(), "file"
    except OSError:
        pass
    try:
        import subprocess
        r = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=5, cwd=PROJECT_ROOT)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), "git"
    except Exception:
        pass
    return "", ""


def operator():
    return operator_source()[0]


def write_operator(name):
    """Create or update ~/.config/tksfw/user.toml with the operator name, keeping the other keys
    (`home`, recorded by `ks self install`)."""
    name = name.strip().replace('"', "'")
    if not name:
        raise ValueError("empty operator name")
    keep = {}
    if os.path.isfile(USER_CONFIG):
        try:
            import tomllib
            with open(USER_CONFIG, "rb") as fh:
                keep = {k: v for k, v in tomllib.load(fh).items() if k not in ("schema", "name")}
        except Exception as e:
            log(f"write_operator: could not read {USER_CONFIG}: {e}")
    os.makedirs(os.path.dirname(USER_CONFIG), exist_ok=True)
    lines = ["# TKSfw per-user configuration (read by the hooks, new_entry_id.py and ks)", "schema = 1",
             f'name = "{name}"          # OwnerSessionUserName on every ledger entry you write']
    for k, v in keep.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
    with open(USER_CONFIG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return USER_CONFIG


def config_view(payload):
    """The configuration the model was told about (or should be): routing table, pin, armed flag,
    operator, config.toml hash. Compared at every prompt against the session record → change notice."""
    view = {"enabled": armed()[0], "operator": operator() or "", "models_hash": None,
            "routing": None, "routing_how": None, "selected": None, "hil": None}
    try:
        if os.path.isfile(MODELS_TOML):
            view["models_hash"] = sha256_file(MODELS_TOML)
            try:
                sys.path.insert(0, VALIDATOR_DIR)
                import validate_yaml_log as V
                view["hil"] = V.hil_describe(V.hil_policy(os.path.join(WORKAREA, "decisions.yaml")))
            except Exception as e:
                log(f"config_view: hil: {e}")
            import route_model as RM
            table = RM.load_table()
            if table:
                key, _tab, how = RM.select_routing(table, RM.detect_harness(payload, None), payload)
                view["routing"], view["routing_how"], view["selected"] = key, how, table.get("selected")
                view["main_model"] = ((_tab or {}).get(RM.MAIN_TIER) or {}).get("model") if _tab else None
    except Exception as e:
        log(f"config_view: {type(e).__name__}: {e}")
    return view


def config_changes(payload, update=True):
    """Human-readable lines for configuration that changed since this session last looked; stores the
    new view in the session record when `update`. [] when nothing changed or no session record."""
    rec = session_record(payload)
    if not rec:
        return []
    now = config_view(payload)
    old = rec.get("config")
    lines = []
    if old is not None:
        if now["routing"] != old.get("routing") or now["selected"] != old.get("selected"):
            lines.append(f"Model routing now [routing.{now['routing']}] via {now['routing_how']}"
                         + (" — THIS SESSION ONLY (`ks routing use … --session`); other sessions keep the project routing" if now.get("routing_how") == "session override" else "")
                         + (f" (pinned: selected = \"{now['selected']}\")" if now.get("selected") and now.get("routing_how") != "session override" else "")
                         + f" — was [routing.{old.get('routing')}]. Applies to the next spawn; record the model the hook reports."
                         + (f" Main session: this session keeps the model it was launched with; the judge-tier model of the new table is `{now['main_model']}` — "
                            f"tell the operator to switch now with `/model {now['main_model']}` (Claude Code) or `/model` (Codex); `ks` has already written it for the next launch."
                            if now.get("main_model") else ""))
        if now.get("hil") != old.get("hil") and old.get("hil") is not None:
            lines.append(f"HIL threshold now {now['hil']} — was {old.get('hil')}. Applies to the next decision entry; pending decisions are re-marked in STATE.md.")
        elif now["models_hash"] != old.get("models_hash") and now["routing"] == old.get("routing") and now["selected"] == old.get("selected"):
            lines.append(f"`{CONFIG_TOML_REL}` changed (tiers/roles/limits) — applies to the next spawn.")
        if now["operator"] != old.get("operator"):
            lines.append(f"Operator now `{now['operator'] or 'UNKNOWN'}` (was `{old.get('operator') or 'UNKNOWN'}`) — use it as OwnerSessionUserName from here on.")
        if now["enabled"] != old.get("enabled"):
            lines.append("Framework " + ("ARMED again in this project." if now["enabled"] else "DISARMED in this project (hooks inert)."))
    if update and (old is None or lines):
        rec["config"] = now
        try:
            atomic_write(os.path.join(SESSIONS_DIR, rec["token"] + ".json"), json.dumps(rec, indent=1))
        except Exception:
            pass
    return lines


def hashes_path(token):
    return os.path.join(STATE_DIR, f"hashes.{token}.json") if token else HASHES


def session_ids_path(token):
    """Per-session view of ledger/plan IDs last seen: attribution of a ledger write is 'what is new
    relative to what THIS session saw', independent of which session's hook indexed it first."""
    return os.path.join(STATE_DIR, f"ids.{token}.json")


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


def _rel_input(path):
    """Project-relative path for a path supplied by the harness (tool input), symlink-safe: macOS spells
    temp dirs `/var/folders/…` while cwd resolves to `/private/var/folders/…`; both must map to the same
    rel as the snapshot walk produces. Only used for tool-input paths — the walk itself stays literal."""
    try:
        rel = os.path.relpath(os.path.realpath(path), os.path.realpath(PROJECT_ROOT))
    except ValueError:                                     # different drives (Windows)
        rel = os.path.relpath(path, PROJECT_ROOT)
    return rel.replace("\\", "/")


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
        if base.startswith(ARCHIVE_REL + "/"):
            name = base[len(ARCHIVE_REL) + 1:]
            if name in ARCHIVE_LEDGERS:
                return "archive:" + name[:-5]  # cumulative archive of a ledger (append-only, never a covering entry)
            if name == "tasks.md":
                return "plan-archive"
            return None
        if "/" in base:
            return None                       # agent work areas: not tracked
        m = SHARD_RE.match(base)
        if m:
            return "ledger:" + m.group(1)     # session shard <ledger>.<token>.yaml
        if base in LEDGER_FILES:
            return "ledger:" + base[:-5]      # legacy unsuffixed shard (read-only) or deliverables registry
        if base == "tasks-archive.md":
            return "plan-archive"             # legacy location (pre-1.5.0) of archive/tasks.md
        if base in PLAN_FILES:
            return "plan"
        return None                           # STATE.md, scratch
    if rel.startswith(MIRROR_PREFIXES):
        return None                           # generated mirrors (skills, agent definitions), not sources
    lc = layer_class(rel)
    if lc:
        return lc                             # L3/L4 project layers (2.2.0): watched inputs
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
    try:
        for name in os.listdir(WORKAREA):
            if SHARD_RE.match(name) and os.path.isfile(os.path.join(WORKAREA, name)):
                files.add(f"{WORKAREA_REL}/{name}")
    except FileNotFoundError:
        pass
    for name in ARCHIVE_LEDGERS + ("tasks.md",):
        p = os.path.join(WORKAREA, ARCHIVE_REL, name)
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
    for rel in layer_paths().values():                    # L3/L4 (2.2.0)
        if os.path.isfile(os.path.join(PROJECT_ROOT, rel)) and not _ignored(rel):
            files.add(rel)
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


# ----------------------------------------------------------------------------- ID index (1.4.0)
_TASK_LINE = re.compile(r"^\s*-\s*\[[ xX]\]\s+([A-Za-z0-9._-]+)\s")


def ledger_ids(rel):
    """{id: owner_token} for a ledger (entries) or a plan file (TaskIDs, owner ""). {} when absent."""
    path = os.path.join(PROJECT_ROOT, rel)
    if not os.path.isfile(path):
        return {}
    name = os.path.basename(rel)
    if name in PLAN_FILES:
        out = {}
        try:
            for line in open(path, encoding="utf-8", errors="replace"):
                m = _TASK_LINE.match(line)
                if m:
                    out.setdefault(m.group(1), "")
        except OSError:
            pass
        return out
    out = {}
    for eid, fields in load_entries(path):
        owner = fields.get("OwnerSessionId") if isinstance(fields, dict) else None
        out[str(eid)] = str(owner) if owner else ""
    return out


def paths_from_tool_input(payload):
    """Project-relative paths the triggering tool call names (Claude Code Write/Edit/MultiEdit/
    NotebookEdit `file_path`; Codex apply_patch '*** Update/Add/Delete File:' lines). Set of rel paths."""
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    out = set()
    for k in ("file_path", "path", "notebook_path"):
        v = ti.get(k)
        if isinstance(v, str) and v:
            out.add(_rel_input(v if os.path.isabs(v) else os.path.join(PROJECT_ROOT, v)))
    for k in ("patch", "input", "command"):
        v = ti.get(k)
        if isinstance(v, list):
            v = " ".join(str(x) for x in v)
        if isinstance(v, str) and "*** " in v:
            for m in re.finditer(r"\*\*\* (?:Update|Add|Delete) File: (.+)", v):
                p = m.group(1).strip()
                out.add(_rel_input(p if os.path.isabs(p) else os.path.join(PROJECT_ROOT, p)))
    return out


def _is_indexed(rel):
    cls = classify(rel) or ""
    return cls.startswith("ledger:") or cls.startswith("archive:") or cls in ("plan", "plan-archive")


def _index_entry(index, rel):
    e = index.get(rel)
    if isinstance(e, dict) and "ids" in e:
        return e
    if isinstance(e, dict):                                # pre-1.4.0 shape {id: owner}
        return {"hash": None, "ids": e}
    return None


def track_ids(changed, after, payload, token):
    """Project-wide ID tracking (independent of this session's hash diff, so an A-B-A rewrite that
    restores an older byte-identical file is still caught): for every ledger/plan file whose content
    hash differs from the one last indexed by ANY hook run, recompute its IDs, attach added_ids /
    removed_ids to the matching change (synthesising one when this session's diff did not see it),
    and store the new hash+ids. Then attribute every change (own | external | ambiguous).
    Must run under `locked()`."""
    index = load_json(ID_INDEX, {}) or {}
    by_path = {c["path"]: c for c in changed}
    for rel in list(index) + [r for r in after if _is_indexed(r) and r not in index]:
        if not _is_indexed(rel):
            continue
        h = after.get(rel)                                  # None = file gone
        prev = _index_entry(index, rel)
        if prev is not None and prev.get("hash") == h:
            continue                                        # unchanged since last indexed
        now = ledger_ids(rel) if h is not None else {}
        before = prev["ids"] if prev is not None else None
        added = {i: o for i, o in now.items() if before is None or i not in before}
        removed = {i: o for i, o in (before or {}).items() if i not in now}
        c = by_path.get(rel)
        if c is None and prev is not None and (added or removed):
            c = {"path": rel, "kind": "deleted" if h is None else "modified", "class": classify(rel), "synthetic": True}
            changed.append(c)
            by_path[rel] = c
        if c is not None:
            c["added_ids"], c["removed_ids"] = added, removed
        index[rel] = {"hash": h, "ids": now}
    # per-session view → attribution of ledger writes by content
    view = load_json(session_ids_path(token), {}) if token else {}
    for c in changed:
        rel = c["path"]
        if (c.get("class") or "").startswith(("ledger:", "archive:")):
            cur = _index_entry(index, rel)
            now = cur["ids"] if cur else {}
            seen = view.get(rel)
            c["new_for_session"] = {i: o for i, o in now.items() if seen is None or i not in seen}
    if token:
        for rel in after:
            if _is_indexed(rel):
                cur = _index_entry(index, rel)
                view[rel] = cur["ids"] if cur else {}
        for rel in [r for r in view if r not in after]:
            view.pop(rel, None)
        atomic_write(session_ids_path(token), json.dumps(view, indent=0, sort_keys=True))
    named = paths_from_tool_input(payload)
    others = bool(other_active_sessions(payload))
    for c in changed:
        cls = c.get("class") or ""
        st = shard_token(c["path"])
        if st is not None and st != "" and token and st != token:
            c["attrib"] = "external"                     # another session's shard: never ours, whatever the tool said
            continue
        added = c.get("new_for_session") or c.get("added_ids") or {}
        if cls.startswith(("ledger:", "archive:")) and added:
            owners = set(added.values())
            if token and all(o and o != token for o in owners):
                c["attrib"] = "external"
                continue
            if token and any(o == token for o in owners):
                c["attrib"] = "own"
                continue
        if c["path"] in named:
            c["attrib"] = "own"
        elif others:
            c["attrib"] = "ambiguous"
        else:
            c["attrib"] = "own"
    atomic_write(ID_INDEX, json.dumps(index, indent=0, sort_keys=True))
    return changed


def seed_snapshot(payload):
    """SessionStart: create the session record (token) and this session's baseline snapshot; index
    ledger/plan IDs not yet indexed. Under `locked()`."""
    token = session_token(payload, create=True)
    after, _globs = snapshot()
    hp = hashes_path(token)
    if load_json(hp, None) is None:
        atomic_write(hp, json.dumps(after, indent=0, sort_keys=True))
    index = load_json(ID_INDEX, {}) or {}
    for rel, h in after.items():
        if _is_indexed(rel) and rel not in index:
            index[rel] = {"hash": h, "ids": ledger_ids(rel)}
    atomic_write(ID_INDEX, json.dumps(index, indent=0, sort_keys=True))
    vp = session_ids_path(token)
    if load_json(vp, None) is None:
        atomic_write(vp, json.dumps({rel: ledger_ids(rel) for rel in after if _is_indexed(rel)}, indent=0, sort_keys=True))
    return token


def record_changes(payload, phase, tool_name=None, tool_use_id=None):
    """Hash the watched set, compare to THIS SESSION's baseline, attribute and journal the delta,
    store the new baseline. Returns (changed, first_run). Must be called under `locked()`."""
    token = session_token(payload, create=True)
    touch_session(payload)
    hp = hashes_path(token)
    before = load_json(hp, None)
    after, globs = snapshot()
    first_run = before is None
    changed = [] if first_run else diff(before, after, globs)
    if first_run:
        index = load_json(ID_INDEX, {}) or {}
        for rel, h in after.items():
            if rel not in index and _is_indexed(rel):
                index[rel] = {"hash": h, "ids": ledger_ids(rel)}
        atomic_write(ID_INDEX, json.dumps(index, indent=0, sort_keys=True))
    elif phase == "tool":
        track_ids(changed, after, payload, token)             # may append synthetic changes
    elif changed:
        track_ids(changed, after, payload, token)
    delegation = bool(tool_name and tool_name in DELEGATION_TOOLS)
    if changed or delegation:
        append_journal({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "harness": harness(payload),
            "session_id": payload.get("session_id"),
            "session": token,
            "turn": turn_key(payload),
            "phase": phase,                       # tool | prompt | session
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "delegation": delegation,
            "changed": changed,
        })
    if first_run or changed:
        atomic_write(hp, json.dumps(after, indent=0, sort_keys=True))
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


def external_changes(entries):
    """Changes attributed to other sessions within the given journal entries: [(path, session)]."""
    out = []
    for e in entries:
        for c in e.get("changed", []):
            if c.get("attrib") == "external":
                owners = {o for o in (c.get("new_for_session") or c.get("added_ids") or {}).values() if o}
                out.append((c["path"], ",".join(sorted(owners)) or "?"))
    return out


def shard_token(rel):
    """Token of a session shard, "" for a legacy unsuffixed ledger, None for anything else."""
    base = os.path.basename(rel)
    m = SHARD_RE.match(base)
    if m:
        return m.group(2)
    if base in LEDGER_FILES and base != "deliverables.yaml" and rel == f"{WORKAREA_REL}/{base}":
        return ""
    return None


def shard_path(kind, token):
    """Project-relative path of a session's shard for a ledger kind."""
    return f"{WORKAREA_REL}/{kind}.{token}.yaml"


def ledger_paths(kind, archive=False):
    """All absolute files holding entries of `kind`: legacy + every shard (+ archive)."""
    out = []
    p = os.path.join(WORKAREA, kind + ".yaml")
    if os.path.isfile(p):
        out.append(p)
    try:
        for name in sorted(os.listdir(WORKAREA)):
            m = SHARD_RE.match(name)
            if m and m.group(1) == kind:
                out.append(os.path.join(WORKAREA, name))
    except FileNotFoundError:
        pass
    if archive:
        a = os.path.join(WORKAREA, ARCHIVE_REL, kind + ".yaml")
        if os.path.isfile(a):
            out.append(a)
    return out


def load_kind(kind, archive=False):
    """Merged (id, fields) entries of a ledger kind across legacy + shards (+ archive), with the
    source file added as fields['_file'] (relative name) for readers that care."""
    out = []
    for p in ledger_paths(kind, archive):
        rel = os.path.relpath(p, WORKAREA)
        for eid, f in load_entries(p):
            if isinstance(f, dict):
                f = dict(f, _file=rel)
            out.append((eid, f))
    return out


def sync_conflicts():
    """Files in the workarea that look like a ledger/plan but are not a canonical name — what Box,
    Dropbox or OneDrive leave behind after a write collision ('changes (1).yaml',
    'tasks (conflicted copy).md', 'events.7Kd2Rf9Q-host.yaml'). Never read, must be merged by hand."""
    out = []
    try:
        names = os.listdir(WORKAREA)
    except FileNotFoundError:
        return out
    for n in names:
        if not os.path.isfile(os.path.join(WORKAREA, n)):
            continue
        if n in LEDGER_FILES or n in PLAN_FILES or SHARD_RE.match(n) or n == "STATE.md":
            continue
        if LEDGER_LIKE_RE.match(n):
            out.append(n)
    return sorted(out)


def archive_path_for(rel):
    """Project-relative archive file that may legitimately receive IDs leaving `rel` (or None)."""
    cls = classify(rel) or ""
    if cls.startswith("ledger:"):
        name = cls.split(":", 1)[1] + ".yaml"
        return f"{WORKAREA_REL}/{ARCHIVE_REL}/{name}" if name in ARCHIVE_LEDGERS else None
    if cls == "plan":
        return f"{WORKAREA_REL}/{ARCHIVE_REL}/tasks.md"
    return None


def unlogged(entries):
    """Order-based, deterministic completeness check over journal entries (agent phases only):
      deliverable  edit to a registry-matched deliverable AFTER the last changes.yaml write
      framework    edit to .agents/.codex/.claude/** or a root instruction file AFTER the last
                   changes.yaml write
      layer        edit to the L3/L4 project layer files (KS_PROJECT.md → ARCHETYPE, KS_SPEC.md →
                   PROJECT) AFTER the last changes.yaml write (2.2.0)
      handoff      a delegation AFTER the last handoffs.yaml OR events.yaml write
    Returns (flags dict, paths dict) where paths lists the offending files."""
    last = {"deliverable": -1, "framework": -1, "layer": -1, "delegation": -1,
            "changes": -1, "handoffs": -1, "events": -1}
    paths = {"deliverable": [], "framework": [], "layer": []}
    i = 0
    for e in entries:
        if e.get("phase") not in (None, "tool"):
            continue                              # external edits are not the agent's to log
        i += 1
        if e.get("delegation"):
            last["delegation"] = i
        for c in e.get("changed", []):
            cls = c.get("class") or ""
            if c.get("attrib") == "external":
                continue                          # another session's write: neither ours to log nor a cover
            if cls.startswith("layer:"):
                cls = "layer"
            if cls == "ledger:changes":
                last["changes"] = i
                paths["deliverable"].clear(); paths["framework"].clear(); paths["layer"].clear()
            elif cls == "ledger:handoffs":
                last["handoffs"] = i
            elif cls == "ledger:events":
                last["events"] = i
            elif cls in ("deliverable", "framework", "layer"):
                last[cls] = i
                if c["path"] not in paths[cls]:
                    paths[cls].append(c["path"])
    flags = {
        "deliverable": last["deliverable"] >= 0 and last["deliverable"] > last["changes"],
        "framework": last["framework"] >= 0 and last["framework"] > last["changes"],
        "layer": last["layer"] >= 0 and last["layer"] > last["changes"],
        "handoff": last["delegation"] >= 0 and (last["delegation"] > last["handoffs"]
                                                or last["delegation"] > last["events"]),
    }
    return flags, paths
