#!/usr/bin/env python3
"""Agent definitions: neutral source → harness mirrors (shared by track_edits.py and sync_harness.py).

  .agents/agents/<name>.toml      SOURCE (harness-neutral; the only file anyone edits)
      ──►  .codex/agents/<name>.toml    Codex mirror: source text with `model` / `model_reasoning_effort`
                                        rendered from the routing tier (codex_agent_files = "inline")
                                        or removed ("strip"); first line is a marker comment
      ──►  .claude/agents/<name>.md     Claude Code mirror: frontmatter name, description, model, effort,
                                        tools (read-only sandbox → read-only tool set); body =
                                        developer_instructions; marker comment after the frontmatter

Mirrors are managed files: identified by their marker, refreshed when the rendering changes, removed
when the source disappears; a file at a mirror path WITHOUT the marker is a hand-made file and is
reported as a conflict, never touched. Both mirror directories are excluded from the edit-hash watch
set (hooklib.classify), so only the source counts as a framework edit.

Rendering is triggered (a) by track_edits.py right after a changed source passes the define-agent
validator — no manual step, works in plugin mode too — and (b) in bulk by sync_harness.py --models
(after editing config.toml) and --check. Standard library only.
"""
import sys
sys.dont_write_bytecode = True
import os
import re
import json
import hashlib
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402
import route_model as RM  # noqa: E402

SRC_DIR = H.AGENTS_SRC
CODEX_DIR = os.path.join(H.PROJECT_ROOT, ".codex", "agents")
CLAUDE_DIR = os.path.join(H.PROJECT_ROOT, ".claude", "agents")
TOML_MARKER = "# tksfw:mirror source={src} sha256={sha} — generated from .agents/agents/ by the TKSfw hooks; edit the SOURCE, not this file"
MD_MARKER = "<!-- tksfw:mirror source={src} sha256={sha} — generated from .agents/agents/ by the TKSfw hooks; edit the SOURCE, not this file -->"
MARKER_TAG = "tksfw:mirror "
TIER_COMMENT = re.compile(r"^\s*#\s*tksfw-tier\s*:\s*([A-Za-z0-9_-]+)", re.M)
TOP_KEY = {"model": re.compile(r'^model\s*=\s*"[^"]*"\s*$', re.M),
           "model_reasoning_effort": re.compile(r'^model_reasoning_effort\s*=\s*"[^"]*"\s*$', re.M)}
CLAUDE_EFFORT = {"minimal": "low", "low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "max"}
READ_ONLY_TOOLS = "Read, Glob, Grep, WebFetch, WebSearch"


def rel(p):
    return os.path.relpath(p, H.PROJECT_ROOT).replace("\\", "/")


# ----------------------------------------------------------------------------- sources
def source_files():
    if not os.path.isdir(SRC_DIR):
        return []
    return sorted(os.path.join(SRC_DIR, f) for f in os.listdir(SRC_DIR)
                  if f.endswith(".toml") and not f.startswith("."))


def load_validator():
    """The define-agent validator module (plugin or in-project layout), or None."""
    v = os.path.join(os.path.dirname(H.AGENT_VALIDATOR), "validate_agent.py")
    if not os.path.isfile(v):
        return None
    spec = importlib.util.spec_from_file_location("validate_agent", v)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def agent_tier(table, text, data):
    """Tier from a `# tksfw-tier: <tier>` comment, else from the agent name via [roles]."""
    m = TIER_COMMENT.search(text)
    if m:
        return m.group(1), "comment"
    _role, tier, _base = RM.resolve_role(table, str(data.get("name") or ""))
    return tier, "name"


# ----------------------------------------------------------------------------- rendering
def render_toml(text, model, effort):
    """Set/insert (or remove, when None) the two top-level keys; everything else byte-identical."""
    out = text
    for key, val in (("model", model), ("model_reasoning_effort", effort)):
        line = f'{key} = "{val}"' if val else None
        if TOP_KEY[key].search(out):
            if line:
                out = TOP_KEY[key].sub(line, out, count=1)
            else:
                out = re.sub(rf'^{key}\s*=\s*"[^"]*"\s*\n?', "", out, count=1, flags=re.M)
        elif line:
            anchor = re.search(r'^model\s*=.*$', out, re.M) if key == "model_reasoning_effort" else None
            anchor = anchor or re.search(r'^name\s*=.*$', out, re.M)
            if anchor:
                out = out[:anchor.end()] + "\n" + line + out[anchor.end():]
            else:
                out = line + "\n" + out
    return out


def render_claude(data, model, effort, src_rel, sha):
    desc = str(data.get("description") or "").replace("\n", " ").strip()
    body = str(data.get("developer_instructions") or "").rstrip()
    fm = [f"name: {data.get('name')}", f"description: {json.dumps(desc, ensure_ascii=False)}"]
    if model:
        fm.append(f"model: {model}")
    if effort and CLAUDE_EFFORT.get(effort):
        fm.append(f"effort: {CLAUDE_EFFORT[effort]}")
    if str(data.get("sandbox_mode") or "") == "read-only":
        fm.append(f"tools: {READ_ONLY_TOOLS}")
    return "---\n" + "\n".join(fm) + "\n---\n" + MD_MARKER.format(src=src_rel, sha=sha) + "\n\n" + body + "\n"


def render_one(path, table, tab_codex, tab_claude, validator):
    """Compute both mirror texts for one source. Returns (name, codex_text, claude_text, errors)."""
    text = open(path, encoding="utf-8").read()
    try:
        data = RM.tomllib.loads(text)
    except Exception as e:
        return None, None, None, [f"invalid TOML: {e}"]
    name = str(data.get("name") or os.path.splitext(os.path.basename(path))[0])
    tier, _how = agent_tier(table, text, data)
    if tier is None or tier not in (table.get("tiers") or {}):
        return name, None, None, [f"no tier: add `# tksfw-tier: <tier>` or a [roles] entry for {name!r}"]
    ec, ea = tab_codex.get(tier) or {}, tab_claude.get(tier) or {}
    if str(table.get("codex_agent_files") or "inline") == "strip":
        body = render_toml(text, None, None)
    else:
        body = render_toml(text, ec.get("model"), ec.get("reasoning_effort"))
    if validator is not None:
        models = validator.load_models(RM.models_path())
        errs, _w, _d = validator.validate_text(body, path, models, validator.sibling_names(path))
        if errs:
            return name, None, None, errs
    sha = hashlib.sha256(text.encode()).hexdigest()[:12]
    src_rel = rel(path)
    codex_text = TOML_MARKER.format(src=src_rel, sha=sha) + "\n" + body
    claude_text = render_claude(data, ea.get("model"), ea.get("reasoning_effort"), src_rel, sha)
    return name, codex_text, claude_text, []


def is_managed(path):
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(600)
        return MARKER_TAG in head
    except Exception:
        return False


def write_mirror(dst, content, check, results):
    cur = open(dst, encoding="utf-8").read() if os.path.isfile(dst) else None
    if cur is not None and MARKER_TAG not in cur[:600]:
        results.append(("conflict", rel(dst), "hand-made file at a mirror path — move it to .agents/agents/ or delete it"))
        return
    if cur == content:
        results.append(("ok", rel(dst)))
    elif check:
        results.append(("stale", rel(dst), "mirror differs" if cur else "missing"))
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(content)
        results.append(("wrote", rel(dst)))


def routing_tables(table):
    """(codex_key, codex_tab, claude_key, claude_tab, how) — Claude falls back to the Codex table."""
    key_c, tab_c, how_c = RM.select_routing(table, "codex")
    key_a, tab_a, how_a = RM.select_routing(table, "claude")
    if tab_a is None:
        key_a, tab_a, how_a = key_c, tab_c, how_c + " (codex table reused)"
    return key_c, tab_c, key_a, tab_a, f"codex=[{key_c}] via {how_c}; claude=[{key_a}] via {how_a}"


def remove_mirrors(name, check, results):
    for d, ext in ((CODEX_DIR, ".toml"), (CLAUDE_DIR, ".md")):
        p = os.path.join(d, name + ext)
        if os.path.isfile(p) and is_managed(p):
            if check:
                results.append(("stale", rel(p), "orphan mirror"))
            else:
                os.remove(p)
                results.append(("removed", rel(p)))


def sync(check=False, only=None):
    """Render every source (or `only` = list of source paths) and prune orphan mirrors.
    Returns list of (status, path[, detail]); status ∈ info|ok|stale|wrote|removed|conflict|skipped."""
    results = []
    try:
        table = RM.load_table()
    except Exception as e:
        return [("conflict", rel(RM.models_path()), f"cannot parse: {e}")]
    if table is None:
        return [("skipped", rel(RM.models_path()), "no config.toml (routing not configured)")]
    problems = RM.validate(table)
    if problems:
        return [("conflict", rel(RM.models_path()), "; ".join(problems))]
    files = source_files()
    if not files and only is None:
        return [("skipped", rel(SRC_DIR), "no agent definitions")]
    key_c, tab_c, key_a, tab_a, how = routing_tables(table)
    if tab_c is None:
        return [("conflict", rel(RM.models_path()),
                 f"no routing table selected ({how}); use --routing <key> or TKSFW_ROUTING")]
    results.append(("info", f"routing {how}", ""))
    validator = load_validator()
    targets = files if only is None else [p for p in only if os.path.isfile(p)]
    names = set()
    for path in targets:
        name, ctext, atext, errs = render_one(path, table, tab_c, tab_a, validator)
        if name:
            names.add(name)
        if errs:
            results.append(("conflict", rel(path), "not rendered: " + "; ".join(errs)))
            continue
        write_mirror(os.path.join(CODEX_DIR, name + ".toml"), ctext, check, results)
        write_mirror(os.path.join(CLAUDE_DIR, name + ".md"), atext, check, results)
    # orphans: managed mirrors whose source is gone
    all_names = {os.path.splitext(os.path.basename(p))[0] for p in files}
    for d, ext in ((CODEX_DIR, ".toml"), (CLAUDE_DIR, ".md")):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(ext) or f[:-len(ext)] in all_names:
                continue
            p = os.path.join(d, f)
            if only is not None and f[:-len(ext)] not in {os.path.splitext(os.path.basename(x))[0] for x in only}:
                continue
            if is_managed(p):
                if check:
                    results.append(("stale", rel(p), "orphan mirror"))
                else:
                    os.remove(p)
                    results.append(("removed", rel(p)))
    return results
