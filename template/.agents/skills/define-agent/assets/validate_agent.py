#!/usr/bin/env python3
"""Validate Codex custom-agent definitions (.codex/agents/<name>.toml) against the TKS method.

Usage:
    validate_agent.py <file.toml> [...] [--models <models.toml>] [--json] [--quiet]
    validate_agent.py --all [--dir .codex/agents]

Exit codes: 0 = no errors (warnings may be printed), 2 = errors, 1 = usage / file not found.

Errors [E] block the write (the PostToolUse hook calls this); warnings [W] are advisory.
The role vocabulary and naming options come from .agents/models.toml ([roles], [naming]); without
that file the validator falls back to the method's default vocabulary. Standard library only.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json

try:
    import tomllib
except ImportError:
    tomllib = None

DEFAULT_ROLES = ("planner", "builder", "reviewer", "validator", "researcher", "fetcher", "writer")
DEFAULT_BUILTIN = ("explorer", "worker", "default", "general-purpose", "Explore", "Plan")
RESERVED = ("main",)
NAME_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")
DESC_PREFIXES = ("Use PROACTIVELY when", "MUST BE USED for")
KNOWN_KEYS = {"name", "description", "developer_instructions", "model", "model_reasoning_effort",
              "sandbox_mode", "mcp_servers", "skills", "model_instructions_file", "nickname_candidates"}
SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}
SANDBOX_BY_TIER = {"research": "read-only", "judge": "read-only", "build": "workspace-write"}
MAX_TOKENS = 3
MIN_TOKEN_LEN = 3
PATH_RE = re.compile(r"(^|\s|`)[\w./-]*[/.][\w./*-]+")          # something that looks like a path/glob
SUCCESS_WORDS = ("success", "criteria", "return", "deliver", "output", "acceptance", "done when")


# ----------------------------------------------------------------------------- models.toml
def find_models(start):
    cur = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start))
    while True:
        p = os.path.join(cur, ".agents", "models.toml")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_models(path):
    if not path or tomllib is None or not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def vocabulary(models):
    """(roles→tier, builtin names, codex_agent_files mode)."""
    if not models:
        return {r: None for r in DEFAULT_ROLES}, set(DEFAULT_BUILTIN), "inline"
    roles = dict(models.get("roles") or {})
    naming = models.get("naming") or {}
    builtin = set(naming.get("builtin_agents") or DEFAULT_BUILTIN)
    for b in builtin:
        roles.pop(b, None)
    return roles, builtin, str(models.get("codex_agent_files") or "inline")


# ----------------------------------------------------------------------------- validation
def validate_text(text, path, models=None, siblings=()):
    """Return (errors, warnings, data). `siblings` = other agent names in the directory."""
    E, W = [], []
    if tomllib is None:
        return ["python >= 3.11 required (tomllib)"], W, {}
    try:
        data = tomllib.loads(text)
    except Exception as e:
        return [f"invalid TOML: {e}"], W, {}
    roles, builtin, mode = vocabulary(models)

    for key in ("name", "description", "developer_instructions"):
        v = data.get(key)
        if not isinstance(v, str) or not v.strip():
            E.append(f"`{key}` is required and must be a non-empty string")
    for key in data:
        if key not in KNOWN_KEYS:
            W.append(f"unknown key `{key}` — Codex documents only: {', '.join(sorted(KNOWN_KEYS))}")

    name = data.get("name") if isinstance(data.get("name"), str) else ""
    tier = None
    if name:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem != name:
            E.append(f"filename `{stem}.toml` must equal name `{name}`")
        if name in RESERVED:
            E.append(f"`{name}` is reserved for the root session; no agent definition may use it")
        elif name in builtin:
            E.append(f"`{name}` is a harness built-in agent name, not a method role; name the agent <family>-<role>")
        elif not NAME_RE.match(name):
            E.append(f"name `{name}` must be lowercase letters and hyphens only (`<family>-<role>`)")
        else:
            tokens = name.split("-")
            if len(tokens) > MAX_TOKENS:
                E.append(f"name `{name}` has {len(tokens)} tokens; ceiling is {MAX_TOKENS} (target 2)")
            role = tokens[-1]
            if role in roles:
                tier = roles[role]
            elif role in builtin:
                E.append(f"role `{role}` is a harness built-in name, not a method role")
            else:
                E.append(f"role `{role}` (last token) is not in the vocabulary {sorted(roles)} — "
                         f"pick one or extend [roles] in .agents/models.toml deliberately")
            short = [t for t in tokens if len(t) < MIN_TOKEN_LEN]
            if short:
                W.append(f"token(s) {short} look like abbreviations; use full plain words")
        if name in siblings:
            E.append(f"name `{name}` is already used by another file in the directory")

    desc = data.get("description") if isinstance(data.get("description"), str) else ""
    if desc and not desc.lstrip().startswith(DESC_PREFIXES):
        E.append("`description` must start with \"Use PROACTIVELY when...\" or \"MUST BE USED for...\"")

    di = data.get("developer_instructions") if isinstance(data.get("developer_instructions"), str) else ""
    if di:
        if len(di.strip()) < 80:
            W.append("`developer_instructions` is very short; state scope, file paths and success criteria")
        if not PATH_RE.search(di):
            W.append("`developer_instructions` names no file path or glob (relevant paths are required)")
        if not any(w in di.lower() for w in SUCCESS_WORDS):
            W.append("`developer_instructions` states no success criteria / expected return")

    sm = data.get("sandbox_mode")
    if sm is not None:
        if sm not in SANDBOX_MODES:
            E.append(f"`sandbox_mode` must be one of {sorted(SANDBOX_MODES)}")
        elif tier and SANDBOX_BY_TIER.get(tier) and sm != SANDBOX_BY_TIER[tier] and sm != "danger-full-access":
            W.append(f"tier `{tier}` normally runs `{SANDBOX_BY_TIER[tier]}`, file says `{sm}`")

    if "model" in data or "model_reasoning_effort" in data:
        if mode == "strip":
            E.append("`model`/`model_reasoning_effort` must not be hand-written (codex_agent_files = \"strip\"); "
                     "models are routed from .agents/models.toml")
        else:
            W.append("`model`/`model_reasoning_effort` are rendered by sync_harness.py --models from the "
                     "routing table; hand-written values will be overwritten")
    return E, W, data


def validate_file(path, models_path=None, siblings=None):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return [f"file not found: {path}"], [], {}
    models = load_models(models_path or find_models(path))
    if siblings is None:
        siblings = sibling_names(path)
    return validate_text(text, path, models, siblings)


def sibling_names(path):
    """Names declared by the OTHER .toml files in the same directory."""
    names = set()
    d = os.path.dirname(os.path.abspath(path))
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if not f.endswith(".toml") or os.path.abspath(os.path.join(d, f)) == os.path.abspath(path):
            continue
        try:
            with open(os.path.join(d, f), "rb") as fh:
                n = tomllib.load(fh).get("name")
            if isinstance(n, str):
                names.add(n)
        except Exception:
            continue
    return names


# ----------------------------------------------------------------------------- cli
def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    quiet = "--quiet" in args
    models_path = None
    if "--models" in args:
        models_path = args[args.index("--models") + 1]
    files = []
    if "--all" in args:
        d = args[args.index("--dir") + 1] if "--dir" in args else os.path.join(".codex", "agents")
        files = sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".toml")) if os.path.isdir(d) else []
    skip = {"--json", "--quiet", "--all"}
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--models", "--dir"):
            i += 2
            continue
        if a not in skip and not a.startswith("--"):
            files.append(a)
        i += 1
    if not files:
        print(__doc__)
        sys.exit(1)
    worst = 0
    out = {}
    for f in files:
        E, W, _ = validate_file(f, models_path)
        out[f] = {"errors": E, "warnings": W}
        if E:
            worst = 2
        if as_json or quiet:
            continue
        if not E and not W:
            print(f"{f}: ok")
        for e in E:
            print(f"{f}: ERROR {e}")
        for w in W:
            print(f"{f}: warning {w}")
    if as_json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    sys.exit(worst)


if __name__ == "__main__":
    main()
