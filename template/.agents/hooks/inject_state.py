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
  3. Emits `hookSpecificOutput.additionalContext` = a short preamble + STATE.md, hard-capped at
     MAX_CHARS. Both harnesses spill oversized hook output to a temp file and hand the model a
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


def main():
    H.guard()
    payload = H.read_payload()
    source = str(payload.get("source") or "startup")
    token, session_line = "", ""
    try:
        with H.locked():
            H.prune_sessions()
            token = H.seed_snapshot(payload)             # per-session baseline + ID index
            H.record_changes(payload, "session")
            others = H.other_active_sessions(payload)
    except Exception as e:
        H.log(f"inject_state: baseline: {type(e).__name__}: {e}")
        others = []
    op, src = H.operator_source()
    if token:
        shown = op or "UNKNOWN"
        if src == "git":
            shown += " (from git config — set it: new_project.py --set-operator / tksfw-init)"
        session_line = (f"Session token: {token} · Operator: {shown} — every new ledger entry carries "
                        f"`OwnerSessionId: {token}` and `OwnerSessionUserName: {op or '<set TKSFW_USER>'}`; "
                        f"work areas: `workarea.py create <agent> <task-id> --session {token}`.")
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
        sys.exit(0)                                  # nothing to inject (fresh project)

    head = PREAMBLE.get(source, PREAMBLE["startup"])
    routing = routing_summary(payload)
    skew = H.version_skew()
    routing = (skew + "\n" if skew else "") + (session_line + "\n" if session_line else "") + routing
    body = (f"{head}\n{routing}Authoritative files: {H.WORKAREA_REL}/tasks.md and "
            f"{H.WORKAREA_REL}/*.yaml (STATE.md is a generated view). Before writing any of those "
            "YAML files, load the yaml-log-entry skill (schemas + ID minting); before creating or renaming "
            "any .agents/agents/*.toml, load the define-agent skill.\n\n" + content)
    H.emit(H.additional_context("SessionStart", cap(body)))
    sys.exit(0)


if __name__ == "__main__":
    main()
