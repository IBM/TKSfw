#!/usr/bin/env python3
"""SessionStart hook: regenerate STATE.md and inject it as model context — harness-neutral.

Fires on `startup|resume|clear|compact|fork` (the `source` field). This closes the compaction
gap: files the model read via tools are evicted at compaction, while a SessionStart hook with
`source: compact` runs before the next model request in Codex (mid-turn auto-compaction delivers
it to the immediate continuation) and Claude Code re-injects it after every compaction. So the
resume cursor no longer depends on the model remembering to re-read STATE.md.

What it does, in order (all fail-open):
  1. Re-baselines the hash journal (`phase: session`) so edits made while no session was running
     are journaled as external, not blamed on the agent's first tool call.
  2. Rebuilds STATE.md from the ledgers RIGHT NOW (not the stale turn-end copy), so after a
     mid-turn compaction it reflects the current plan and ledger state.
  3. Emits `hookSpecificOutput.additionalContext` assembled from SECTIONS (2.2.0): `state` = a
     short preamble + STATE.md (the only section that is truncated to fit), `layers` = the L3/L4
     project-layer pointer block (paths + status, ≤ 600 B). Each section sits between
     `<!-- tksfw:<id> -->` markers; a failing emitter degrades to an error marker. Hard cap MAX_CHARS. Both harnesses spill oversized hook output to a temp file and hand the model a
     preview instead (Codex ≈ 2,500 tokens by default, Claude Code 10,000 chars); staying under
     the cap keeps the injection intact and keeps project data out of temp directories.

Output shape is identical for both harnesses. Exit code is always 0 (SessionStart cannot block).
"""
import sys
sys.dont_write_bytecode = True
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402
import refresh_state  # noqa: E402
import route_model  # noqa: E402
import layers  # noqa: E402

MAX_CHARS = 9000        # < Claude 10,000-char cap and ≈ Codex 2,500-token default cap

PREAMBLE = {
    "startup": "Session start. Resume cursor below (generated from the ledgers now).",
    "resume":  "Session resumed. Resume cursor below (generated from the ledgers now).",
    "clear":   "Context cleared. Resume cursor below (generated from the ledgers now).",
    "fork":    "Session forked. Resume cursor below (generated from the ledgers now).",
    "compact": ("Context was compacted: tool outputs you read earlier are gone. Resume cursor "
                "below (regenerated now). Re-read tasks.md and the relevant ledgers before "
                "continuing; log pending changes/handoffs listed under 'Un-logged edits'."),
}


def cap(text, limit=MAX_CHARS):
    if len(text) <= limit:
        return text
    marker = "\n… [STATE.md truncated to fit the hook context limit; read the file for the rest]\n"
    return text[: limit - len(marker)] + marker


def routing_summary(payload):
    """One line: which routing table applies to this session (or that spawns will be denied)."""
    try:
        table = route_model.load_table()
        if table is None:
            return ""
        harness = H.harness(payload)
        if harness == "unknown":
            harness = "codex" if route_model.codex_model_provider() else "claude"
        key, tab, how = route_model.select_routing(table, harness)
        if tab is None:
            return ("Model routing: NO [routing.*] table matches this provider — subagent spawns will be "
                    "denied until .agents/models.toml has one (or TKSFW_ROUTING is set).\n")
        tiers = ", ".join(f"{t}={ (tab.get(t) or {}).get('model', '?') }" for t in (table.get("tiers") or {}))
        return f"Model routing [routing.{key}] via {how}: {tiers}.\n"
    except Exception as e:
        H.log(f"inject_state: routing summary: {type(e).__name__}: {e}")
        return ""


def emit_state(payload, ctx):
    """Section `state`: preamble, session/routing lines and STATE.md regenerated from the ledgers now.
    '' on a fresh project (nothing to resume)."""
    source = str(payload.get("source") or "startup")
    token, session_line = "", ""
    try:
        with H.locked():
            H.prune_sessions()
            token = H.seed_snapshot(payload)             # per-session baseline + ID index
            H.record_changes(payload, "session")
            H.config_changes(payload)                    # store the configuration view the model is shown
            others = H.other_active_sessions(payload)
    except Exception as e:
        H.log(f"inject_state: baseline: {type(e).__name__}: {e}")
        others = []
    op, src = H.operator_source()
    if token:
        shown = op or "UNKNOWN"
        if src == "git":
            shown += " (from git config — set it: new_project.py --set-operator / tksfw-init)"
        session_line = (f"Session token: {token} · Operator: {shown} — your ledger files are "
                        f"`{H.WORKAREA_REL}/<ledger>.{token}.yaml` (changes, lessons, handoffs, events, decisions; other sessions' "
                        f"shards and unsuffixed legacy files are READ-ONLY); every new entry carries "
                        f"`OwnerSessionId: {token}` and `OwnerSessionUserName: {op or '<set TKSFW_USER>'}`; "
                        f"work areas: `workarea.py create <agent> <task-id> --session {token}`.")
        conflicts = H.sync_conflicts()
        if conflicts:
            session_line += ("\nWARNING: sync conflict copies in the workarea: " + ", ".join(conflicts)
                             + " — not read by the framework; merge into the canonical files by hand, then delete.")
        if not op:
            session_line += (" OPERATOR UNKNOWN: run `python3 tools/new_project.py --set-operator \"<name>\"` "
                             f"(writes {H.USER_CONFIG}) or export TKSFW_USER — ledger entries need it.")
        if others:
            session_line += ("\n" + f"WARNING: {len(others)} other session(s) active on this project in the last "
                             f"{H.SESSION_ACTIVE_SEC // 60} min (" + ", ".join(f"{d['token']}/{d.get('operator') or '?'}" for d in others[:3])
                             + "). Parallel sessions are tolerated, not a design target: the hooks block lost updates on "
                             "ledgers/tasks.md and attribute changes, but coordinate before editing the same files.")

    content = refresh_state.write_state()
    if not content:
        try:
            with open(H.STATE_MD, encoding="utf-8") as fh:
                content = fh.read()                  # fall back to the last turn-end copy
        except Exception:
            content = ""
    if not content.strip():
        return ""                                    # nothing to resume (fresh project)

    head = PREAMBLE.get(source, PREAMBLE["startup"])
    routing = routing_summary(payload)
    skew = H.version_skew()
    gen = H.generation_line()
    routing = (skew + "\n" if skew else "") + (gen + "\n" if gen else "") + (session_line + "\n" if session_line else "") + routing
    return (f"{head}\n{routing}Authoritative files: {H.WORKAREA_REL}/tasks.md and "
            f"{H.WORKAREA_REL}/*.yaml (STATE.md is a generated view). Before writing any of those "
            "YAML files, load the yaml-log-entry skill (schemas + ID minting); before creating or renaming "
            "any .agents/agents/*.toml, load the define-agent skill.\n\n" + content)


def emit_layers(payload, ctx):
    """Section `layers` (2.2.0): pointer block for the L3/L4 project layers — paths and status, never
    content. '' when nothing resolves. The resolution is kept in ctx so main() can journal the hashes."""
    res = layers.resolve()
    ctx["layers"] = res
    return layers.section(res)


# Emitter registry: (id, priority, function). The assembler renders in this order; `state` is the
# one section that may be truncated to fit the global budget — every other section is small by
# contract (each emitter caps itself) and is reserved first. A failing emitter degrades to a one-line
# error marker; the injection itself never fails.
SECTIONS = (("state", emit_state), ("layers", emit_layers))


def assemble(payload, ctx, limit=MAX_CHARS):
    """Render every section between markers, in SECTIONS order, within `limit` characters: small
    sections are reserved first, `state` receives the remaining budget (capped, never dropped)."""
    def wrap(sid, text):
        return f"<!-- tksfw:{sid} -->\n{text}\n<!-- /tksfw:{sid} -->"
    rendered = {}
    for sid, fn in SECTIONS:
        try:
            text = fn(payload, ctx) or ""
        except Exception as e:
            H.log(f"inject_state: section {sid}: {type(e).__name__}: {e}")
            text = f"<!-- tksfw:{sid} error: emitter failed; see the hooks.log under {H.WORKAREA_REL}/.hook-state/ -->"
        rendered[sid] = text
    reserved = sum(len(wrap(sid, t)) + 2 for sid, t in rendered.items() if t and sid != "state")
    out = []
    for sid, _fn in SECTIONS:
        t = rendered[sid]
        if not t:
            continue
        if t.startswith("<!-- tksfw:") and " error: " in t:
            out.append(t)
        elif sid == "state":
            out.append(wrap(sid, cap(t, max(limit - reserved - len(wrap(sid, "")), 400))))
        else:
            out.append(wrap(sid, t))
    return "\n\n".join(out)


def main():
    H.guard()
    payload = H.read_payload()
    ctx = {}
    body = assemble(payload, ctx)
    if not body.strip():
        sys.exit(0)                                  # nothing to inject (fresh project, no layers)
    H.emit(H.additional_context("SessionStart", body))
    try:
        res = ctx.get("layers")
        if res and res.get("layers"):
            with H.locked():
                layers.journal(res)                  # status baseline for the next start/compaction
    except Exception as e:
        H.log(f"inject_state: layers journal: {type(e).__name__}: {e}")
    sys.exit(0)


if __name__ == "__main__":
    main()
