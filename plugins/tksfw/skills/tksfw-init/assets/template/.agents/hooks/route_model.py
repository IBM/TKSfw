#!/usr/bin/env python3
"""PreToolUse hook: route every subagent spawn to the model of its role tier — harness-neutral.

Matcher (hooks.json): `^(Agent|Task)$|spawn_agent`. Codex exposes `spawn_agent` (alias `Agent`);
Claude Code exposes `Agent` (formerly `Task`).

At every spawn the hook
  1. loads `.agents/config.toml` fresh from disk (so edits apply to the next spawn: no restart,
     no hook re-trust — the script itself does not change),
  2. selects the routing table for the provider this session is connected to
     ($TKSFW_ROUTING → `selected = "<table>"` in config.toml (`ks routing use`) → Codex
     `model_provider` in $CODEX_HOME/config.toml → Claude Code $ANTHROPIC_BASE_URL prefix match →
     [routing.default] → DENY),
  3. resolves the agent's role (full name in [roles], else the -<role> suffix) → tier → model,
  4. returns `permissionDecision: "allow"` + `updatedInput` = the original arguments plus
        Codex:        model, reasoning_effort
        Claude Code:  model                (effort is rendered into .claude/agents/*.md by
                                            sync_harness.py --models; the Agent tool has no
                                            per-invocation effort parameter)
     plus `additionalContext` telling the orchestrator which model the child runs on so the
     Handoff/Event ledger `Model:` field is recorded from fact.
  5. journals the decision to .agents/workarea/.hook-state/routing.jsonl.

Unknown role → DENY (or allow-unchanged when on_unknown_role = "inherit"). Missing routing for
the current provider → DENY with the list of available tables (fail loud, never silently on the
parent's model). No config.toml at all → the hook does nothing (project without routing).
Internal errors → exit 0 silently (fail-open), logged to hooks.log.

Standalone:
  python3 .agents/hooks/route_model.py --print        # resolved table for THIS environment
  python3 .agents/hooks/route_model.py --check        # validate config.toml (exit 1 on problems)
  python3 .agents/hooks/route_model.py --main [--codex|--claude]   # main-session (judge tier) model per harness, JSON
  python3 .agents/hooks/route_model.py --resolve sources-researcher   # one lookup
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402

try:
    import tomllib
except ImportError:                              # Python < 3.11: routing unavailable, fail-open
    tomllib = None

EFFORTS = {"codex": ("minimal", "low", "medium", "high", "xhigh"),
           "claude": ("low", "medium", "high", "xhigh", "max")}
SPAWN_TOOLS = {"Agent", "Task", "spawn_agent"}
ROUTING_LOG = os.path.join(H.STATE_DIR, "routing.jsonl")


# ----------------------------------------------------------------------------- loading
def models_path():
    return os.environ.get("TKSFW_MODELS_FILE") or H.MODELS_TOML


def load_table(path=None):
    """Parsed config.toml or None when absent. Raises on syntax errors (caller decides)."""
    path = path or models_path()
    if not os.path.isfile(path) or tomllib is None:
        return None
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def validate(table, harness=None):
    """List of problems ('' items = none). Checks referential integrity and effort vocab."""
    problems = []
    tiers = table.get("tiers") or {}
    if not tiers:
        problems.append("[tiers] is empty")
    roles = table.get("roles") or {}
    for role, tier in roles.items():
        if tier not in tiers:
            problems.append(f"[roles] {role} → unknown tier {tier!r}")
    routing = table.get("routing") or {}
    if not routing:
        problems.append("no [routing.<provider>] table")
    sel = table.get("selected")
    if sel and str(sel) not in routing:
        problems.append(f"selected = {sel!r} names no [routing.{sel}] table")
    dr = table.get("default_routing")
    if dr and str(dr) not in routing:
        problems.append(f"default_routing = {dr!r} names no [routing.{dr}] table")
    allowed = set(EFFORTS[harness]) if harness in EFFORTS else set(EFFORTS["codex"]) | set(EFFORTS["claude"])
    for key, tab in routing.items():
        for tier in tiers:
            entry = tab.get(tier)
            if entry is None:
                problems.append(f"[routing.{key}] has no entry for tier {tier!r}")
                continue
            if not isinstance(entry, dict) or not isinstance(entry.get("model"), str) or not entry["model"]:
                problems.append(f"[routing.{key}].{tier} needs model = \"<id>\"")
                continue
            eff = entry.get("reasoning_effort")
            if eff is not None and eff not in allowed:
                problems.append(f"[routing.{key}].{tier} reasoning_effort {eff!r} not in {sorted(allowed)}")
        for extra in tab:
            if extra not in tiers and extra != "match":
                problems.append(f"[routing.{key}] unknown key {extra!r} (not a tier)")
    if table.get("on_unknown_role", "deny") not in ("deny", "inherit"):
        problems.append("on_unknown_role must be \"deny\" or \"inherit\"")
    if table.get("codex_agent_files", "inline") not in ("inline", "strip"):
        problems.append("codex_agent_files must be \"inline\" or \"strip\"")
    return problems


# ----------------------------------------------------------------------------- selection
def codex_model_provider():
    """`model_provider` from $CODEX_HOME/config.toml (top-level key only), or None."""
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    cfg = os.path.join(home, "config.toml")
    try:
        with open(cfg, "rb") as fh:
            if tomllib is not None:
                data = tomllib.load(fh)
                v = data.get("model_provider")
                return v if isinstance(v, str) else None
    except FileNotFoundError:
        return None
    except Exception:
        # fall back to a line scan when the file has TOML we cannot parse
        try:
            with open(cfg, encoding="utf-8") as fh:
                for line in fh:
                    m = re.match(r'^\s*model_provider\s*=\s*"([^"]+)"', line)
                    if m:
                        return m.group(1)
                    if line.lstrip().startswith("["):
                        break
        except Exception:
            return None
    return None


def select_routing(table, harness, payload=None, session_override=None):
    """(key, table_or_None, how). Order: session override (`ks routing use --session`, 3.4.0) → TKSFW_ROUTING →
    `selected` → Codex provider match → Claude base URL → default_routing → [routing.default]."""
    routing = table.get("routing") or {}
    so = session_override or (H.session_routing(payload) if payload else None) or os.environ.get("TKSFW_SESSION_ROUTING")
    if so:
        return str(so), routing.get(str(so)), "session override"
    forced = os.environ.get("TKSFW_ROUTING")
    if forced:
        return forced, routing.get(forced), "TKSFW_ROUTING"
    selected = table.get("selected")                     # `ks routing use <table>` — persisted choice
    if selected:
        return str(selected), routing.get(str(selected)), "selected (config.toml)"
    if harness == "codex":
        prov = codex_model_provider()
        if prov:
            for key, tab in routing.items():             # 3.0.0: explicit match first, then key == provider
                m = tab.get("match") or {}
                if str(m.get("codex_model_provider") or "") == prov:
                    return key, tab, "codex model_provider (match)"
            if prov in routing:
                return prov, routing[prov], "codex model_provider"
    if harness == "claude":
        base = (os.environ.get("ANTHROPIC_BASE_URL") or "").rstrip("/")
        if base:
            for key, tab in routing.items():
                m = tab.get("match") or {}
                want = str(m.get("claude_base_url") or "").rstrip("/")
                if want and base.startswith(want):
                    return key, tab, "ANTHROPIC_BASE_URL"
    dr = table.get("default_routing")                    # 3.1.0: named default table
    if dr and str(dr) in routing:
        return str(dr), routing[str(dr)], "default_routing"
    if "default" in routing:
        return "default", routing["default"], "default"
    return None, None, "none"


def detect_harness(payload, tool_name):
    h = H.harness(payload)
    if h != "unknown":
        return h
    if tool_name == "spawn_agent":
        return "codex"
    if tool_name in ("Agent", "Task") or "subagent_type" in (payload.get("tool_input") or {}):
        return "claude"
    return "unknown"


def agent_name(tool_input):
    """Agent identity from the spawn arguments: Claude `subagent_type`; Codex `agent_type`
    (v1) or the `task_name` (v2, which the method sets to the agent name)."""
    for key in ("subagent_type", "agent_type", "agent_name", "task_name", "name"):
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def resolve_role(table, name):
    """(role, tier, agent_base) — agent_base is the name without a v2 `_<task>` suffix. Full name first, then the -<role> suffix, then a
    task_name prefix before the first '_' (v2 convention `<agent-name>_<task>`)."""
    roles = table.get("roles") or {}
    bases = [name] + ([name.split("_", 1)[0]] if "_" in name else [])
    for base in bases:
        for cand in ([base] + ([base.rsplit("-", 1)[1]] if "-" in base else [])):
            if cand in roles:
                return cand, roles[cand], base
    return None, None, name


def resolve(table, name, harness, payload=None, check_agent=True):
    """Full resolution → dict(ok, ...). Never raises for data problems. `check_agent=False` (CLI `--resolve`)
    answers "which model would this name get" without requiring the definition to exist."""
    key, tab, how = select_routing(table, harness, payload)
    if tab is None:
        avail = sorted((table.get("routing") or {}).keys())
        return {"ok": False, "reason": (f"TKSfw routing: no [routing.*] table for this provider "
                                        f"(selection={how}, key={key!r}); available: {avail}. "
                                        f"Set TKSFW_ROUTING=<key> or add the table to .agents/config.toml.")}
    role, tier, base = resolve_role(table, name)
    if tier is None:
        return {"ok": False, "unknown_role": True, "routing": key,
                "reason": (f"TKSfw routing: agent {name!r} has no role in [roles] of .agents/config.toml "
                           f"(known roles: {sorted((table.get('roles') or {}).keys())}). Name agents "
                           f"<family>-<role> per AGENTS.md § Agent Naming, or add the role.")}
    entry = tab.get(tier)
    if not isinstance(entry, dict) or not entry.get("model"):
        return {"ok": False, "reason": f"TKSfw routing: [routing.{key}] has no model for tier {tier!r}."}
    # 3.4.1: the harness will refuse an agent type that does not exist — say so here, with the fix
    builtin = set((table.get("naming") or {}).get("builtin_agents") or []) | {"Explore", "Plan", "general-purpose", "explorer", "worker", "default"}
    if check_agent and base not in builtin:
        src = os.path.join(H.PROJECT_ROOT, ".agents", "agents", base + ".toml")
        if not os.path.isfile(src):
            roles = table.get("roles") or {}
            hint = (f"`{base}` is a ROLE, not an agent — agents are named <family>-<role> (e.g. `report-{base}`). "
                    if base in roles and "-" not in base else "")
            return {"ok": False, "no_agent": True, "routing": key, "role": role, "tier": tier,
                    "reason": (f"TKSfw routing: no agent definition for {base!r} (.agents/agents/{base}.toml missing). {hint}"
                               f"Define it first with the define-agent skill (it renders .claude/agents/{base}.md and "
                               f".codex/agents/{base}.toml), or spawn a built-in type ({', '.join(sorted(b for b in builtin if b[0].isupper() or b == 'general-purpose'))}) "
                               f"and route it by role.")}
        mirror = os.path.join(H.PROJECT_ROOT, ".claude", "agents", base + ".md") if harness == "claude" \
            else os.path.join(H.PROJECT_ROOT, ".codex", "agents", base + ".toml")
        if not os.path.isfile(mirror):
            try:                                          # source exists, mirror missing (copied project, pruned dir): render now
                import agentlib
                agentlib.sync(check=False, only=[src])
            except Exception as e:
                H.log(f"route_model: mirror render for {base}: {e}")
    return {"ok": True, "routing": key, "selected_by": how, "agent": base, "role": role, "tier": tier,
            "model": entry["model"], "reasoning_effort": entry.get("reasoning_effort")}


# ----------------------------------------------------------------------------- output
def nested_spawn(payload):
    """True when the spawn request comes from inside a subagent. Claude Code adds top-level `agent_id` /
    `agent_type` to hook input delivered to a subagent; Codex exposes the thread path/depth. Unknown → False."""
    if isinstance(payload.get("agent_id"), str) and payload.get("agent_id"):
        return True
    if isinstance(payload.get("agent_type"), str) and payload.get("agent_type"):
        return True
    for k in ("parent_thread_id", "parent_agent_id"):
        if payload.get(k):
            return True
    ap = payload.get("agent_path") or payload.get("thread_path")
    if isinstance(ap, str) and ap.strip("/").count("/") >= 1:          # /root/explorer → depth 1
        return True
    d = payload.get("depth") or payload.get("agent_depth")
    return isinstance(d, int) and d > 0


def live_subagents(payload):
    try:
        import subagent_track
        return subagent_track.live_count(session=H.session_token(payload, create=True))
    except Exception as e:
        H.log(f"route_model: live count unavailable: {e}")
        return 0


def deny(reason):
    H.emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}})


def allow(tool_input, res, harness, table=None):
    new = dict(tool_input)
    alias = claude_alias(table or {}, res["tier"]) if harness == "claude" else None
    if alias:
        # Claude Code's Agent tool schema accepts only aliases here; the alias resolves to the routed id
        # through ANTHROPIC_DEFAULT_<ALIAS>_MODEL (written by ks into .claude/settings.local.json), and a
        # custom agent's own frontmatter (.claude/agents/<name>.md, full id) takes precedence anyway.
        new["model"] = alias
    else:
        new["model"] = res["model"]
    if harness == "codex" and res.get("reasoning_effort"):
        new["reasoning_effort"] = res["reasoning_effort"]
    eff = f" ({res['reasoning_effort']})" if res.get("reasoning_effort") else ""
    via = f" (spawned as alias `{alias}` → {res['model']} via ANTHROPIC_DEFAULT_{alias.upper()}_MODEL)" if alias else ""
    ctx = (f"TKSfw routing: {res['agent']} → role {res['role']} → tier {res['tier']} → "
           f"model {res['model']}{eff} [routing.{res['routing']}]{via}. Record `Model: {res['model']}` "
           f"in the handoffs.yaml / events.yaml entries for this delegation.")
    H.emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                   "updatedInput": new, "additionalContext": ctx}})


def journal(entry):
    try:
        H.ensure_state_dir()
        with open(ROUTING_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------- cli
def print_table(harness, session_override=None):
    table = load_table()
    if table is None:
        print(f"no routing: {models_path()} not found" + (" (tomllib unavailable)" if tomllib is None else ""))
        return 1
    key, tab, how = select_routing(table, harness, session_override=session_override)
    print(f"config: {models_path()}")
    print(f"harness={harness}  routing={key!r}  selected_by={how}")
    if tab is None:
        print("NO ROUTING TABLE for this environment — spawns will be denied. Available: "
              + ", ".join(sorted((table.get('routing') or {}).keys())))
        return 1
    for tier, desc in (table.get("tiers") or {}).items():
        e = tab.get(tier) or {}
        roles = sorted(r for r, t in (table.get("roles") or {}).items() if t == tier)
        print(f"  {tier:<9} {e.get('model','?'):<30} effort={e.get('reasoning_effort') or '(default)':<9} roles={', '.join(roles)}")
    return 0


MAIN_TIER = "judge"                                   # the main session orchestrates, plans and judges
CLAUDE_ALIASES = {"research": "haiku", "build": "sonnet", "judge": "opus"}   # override: [claude_aliases] tier = "alias"


def claude_alias(table, tier):
    """Claude Code's Agent tool accepts only the aliases sonnet|opus|haiku|fable in its per-spawn `model`
    parameter (3.3.0). Each tier maps to one alias; `ks` writes ANTHROPIC_DEFAULT_<ALIAS>_MODEL into
    .claude/settings.local.json so the alias resolves to the routed model id (third-party ids included)."""
    ov = table.get("claude_aliases") if isinstance(table.get("claude_aliases"), dict) else {}
    a = str(ov.get(tier) or CLAUDE_ALIASES.get(tier) or "").lower()
    return a if a in ("sonnet", "opus", "haiku", "fable") else None


def main_model(harness, session_override=None):
    """{harness, routing, selected_by, tier, model, reasoning_effort} for the MAIN session of `harness`
    (3.2.0): the judge-tier entry of the table that harness would select. None when no table resolves."""
    table = load_table()
    if table is None:
        return None
    key, tab, how = select_routing(table, harness, session_override=session_override)
    if tab is None:
        return {"harness": harness, "routing": None, "selected_by": how, "tier": MAIN_TIER, "model": None, "reasoning_effort": None}
    e = tab.get(MAIN_TIER) or {}
    out = {"harness": harness, "routing": key, "selected_by": how, "tier": MAIN_TIER,
           "model": e.get("model"), "reasoning_effort": e.get("reasoning_effort")}
    if harness == "claude":                          # alias → id map for ANTHROPIC_DEFAULT_<ALIAS>_MODEL
        out["alias"] = claude_alias(table, MAIN_TIER)
        out["aliases"] = {claude_alias(table, t): (tab.get(t) or {}).get("model") for t in (table.get("tiers") or {}) if claude_alias(table, t)}
    return out


def main():
    args = sys.argv[1:]
    harness_arg = "codex" if "--codex" in args else "claude" if "--claude" in args else None
    so = args[args.index("--session-routing") + 1] if "--session-routing" in args else None   # ks: a session's override
    if "--main" in args:
        out = {h: main_model(h, so) for h in ("codex", "claude")} if not harness_arg else main_model(harness_arg, so)
        print(json.dumps(out, indent=2))
        sys.exit(0)
    if "--check" in args:
        table = load_table()
        if table is None:
            print("no config.toml"); sys.exit(1)
        probs = validate(table, harness_arg)
        print("\n".join(probs) if probs else "config.toml ok")
        sys.exit(1 if probs else 0)
    if "--print" in args:
        sys.exit(print_table(harness_arg or ("codex" if codex_model_provider() else "claude"), so))
    if "--resolve" in args:
        name = args[args.index("--resolve") + 1]
        table = load_table()
        if so:
            os.environ["TKSFW_SESSION_ROUTING"] = so
        print(json.dumps(resolve(table, name, harness_arg or "codex", check_agent=False), indent=2))
        sys.exit(0)

    # ---- hook mode
    H.guard()
    payload = H.read_payload()
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool_name and not (tool_name in SPAWN_TOOLS or tool_name.endswith("spawn_agent")):
        sys.exit(0)                                              # not a spawn: matcher too broad
    try:
        table = load_table()
    except Exception as e:                                       # syntax error: block, say why
        deny(f"TKSfw routing: cannot parse {models_path()}: {e}")
        sys.exit(0)
    if table is None:
        sys.exit(0)                                              # no routing configured
    harness = detect_harness(payload, tool_name)
    deleg = table.get("delegation") if isinstance(table.get("delegation"), dict) else {}
    if deleg.get("deny_nested_spawn", True) and nested_spawn(payload):
        journal({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "turn": H.turn_key(payload), "harness": harness,
                 "tool": tool_name, "allowed": False, "reason": "nested spawn"})
        deny("TKSfw delegation: subagents cannot spawn further subagents — all decomposition happens "
             "from the main session (AGENTS.md § Subagents). Return your result; let `main` delegate.")
        sys.exit(0)
    cap = deleg.get("max_parallel_agents", 4)
    if isinstance(cap, int) and cap > 0:
        live = live_subagents(payload)
        if live >= cap:
            journal({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "turn": H.turn_key(payload), "harness": harness,
                     "tool": tool_name, "allowed": False, "reason": f"parallel cap {live}/{cap}"})
            deny(f"TKSfw delegation: {live} subagents are already running — the limit is {cap} parallel agents "
                 f"per phase ([delegation] max_parallel_agents in {H.MODELS_TOML_REL}). Wait for one to return, "
                 "then spawn (load the `delegate-work` skill for the isolation/handoff procedure).")
            sys.exit(0)
    name = agent_name(tool_input)
    if not name:
        H.log(f"route_model: spawn without agent name; input keys={sorted(tool_input)}")
        if (table.get("on_unknown_role") or "deny") == "inherit":
            sys.exit(0)
        deny("TKSfw routing: spawn has no agent identity (subagent_type / agent_type / task_name). "
             "Name the agent <family>-<role> so it can be routed.")
        sys.exit(0)
    res = resolve(table, name, harness, payload)
    journal({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "turn": H.turn_key(payload), "harness": harness,
             "tool": tool_name, **{k: v for k, v in res.items() if k != "ok"}, "allowed": res["ok"]
             or (res.get("unknown_role") and table.get("on_unknown_role") == "inherit")})
    if res["ok"]:
        allow(tool_input, res, harness, table)
    elif res.get("unknown_role") and (table.get("on_unknown_role") or "deny") == "inherit":
        sys.exit(0)
    else:
        deny(res["reason"])
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                                       # fail-open
        H.log(f"route_model: {type(e).__name__}: {e}")
        sys.exit(0)
