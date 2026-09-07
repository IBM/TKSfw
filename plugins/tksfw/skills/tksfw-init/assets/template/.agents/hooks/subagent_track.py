#!/usr/bin/env python3
"""SubagentStart / SubagentStop hook: keep the set of LIVE subagents so the routing hook can enforce
`[delegation] max_parallel_agents` (AGENTS.md: never more than N parallel agents per phase).

    python3 .agents/hooks/subagent_track.py --start      (SubagentStart)
    python3 .agents/hooks/subagent_track.py --stop       (SubagentStop)

State: .agents/workarea/.hook-state/subagents.json  {"live": {<id>: {"turn", "agent", "ts"}}}
  * id = payload agent_id | tool_use_id | task_name | a counter — whatever both harnesses provide.
  * A main-session Stop clears the set (check_ledgers_on_stop.py calls `clear()`): when `main` stops,
    every child has returned, so a missed SubagentStop can never wedge future spawns.
  * Entries older than TTL_SEC are ignored when counting (belt and braces).
Both harnesses emit these events (Codex: SubagentStart/SubagentStop; Claude Code: same names) and accept
`additionalContext` on SubagentStart — since 2.0.0 the hook injects a ledger briefing into the subagent
(digest.py --agent <name>): its handoff BEGIN, task evidence chain, blocked gates, decisions in force,
open issues, recent lessons. Fail-open, exit 0 always.
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402

STATE = os.path.join(H.STATE_DIR, "subagents.json")
TTL_SEC = 4 * 3600


def load():
    return H.load_json(STATE, {"live": {}})


def save(data):
    H.ensure_state_dir()
    H.atomic_write(STATE, json.dumps(data, ensure_ascii=False, indent=1))


def ident(payload):
    for k in ("agent_id", "subagent_id", "thread_id", "tool_use_id", "task_name"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    return f"anon-{int(time.time() * 1000)}"


def live_count(data=None, turn=None, session=None):
    """Live subagents; with `session` (framework token) only that session's — the cap is per session
    (AGENTS.md: per phase), so two sessions on one project do not share it."""
    data = data if data is not None else load()
    now = time.time()
    n = 0
    for _id, e in (data.get("live") or {}).items():
        if now - float(e.get("ts", 0)) > TTL_SEC:
            continue
        if turn and e.get("turn") and e["turn"] != turn:
            continue
        if session and e.get("session") and e["session"] != session:
            continue
        n += 1
    return n


def clear(session=None):
    """Main-session Stop: drop this session's live entries (all entries when session unknown)."""
    try:
        if not os.path.isfile(STATE):
            return
        if not session:
            save({"live": {}})
            return
        data = load()
        data["live"] = {i: e for i, e in (data.get("live") or {}).items() if e.get("session") and e["session"] != session}
        save(data)
    except Exception:
        pass


def main():
    H.guard()
    payload = H.read_payload()
    start = "--start" in sys.argv
    try:
        with H.locked():
            data = load()
            live = data.setdefault("live", {})
            i = ident(payload)
            if start:
                live[i] = {"turn": H.turn_key(payload), "agent": payload.get("agent_type") or payload.get("subagent_type") or "",
                           "session": H.session_token(payload, create=True), "ts": time.time()}
            else:
                live.pop(i, None)
            save(data)
    except Exception as e:
        H.log(f"subagent_track: {type(e).__name__}: {e}")
    if start:
        brief = briefing(payload)
        if brief:
            H.emit(H.additional_context("SubagentStart", brief))
    sys.exit(0)


def briefing(payload):
    """Ledger context for the subagent (2.0.0): its open handoff BEGIN, the task's evidence chain,
    blocked gates, decisions in force, open issues, recent lessons — bounded by
    [state].subagent_budget_chars. '' when the digest is empty or unavailable."""
    agent = payload.get("agent_type") or payload.get("subagent_type") or ""
    try:
        sys.path.insert(0, H.VALIDATOR_DIR)
        import digest as DG
        lim = DG.limits(H.WORKAREA)
        d = DG.build(H.WORKAREA, agent=agent or None)
        text = DG.format_digest(d, lim, lim.get("subagent_budget_chars", 4000), heading_level="##",
                                title="Ledger briefing")
        if not text:
            return ""
        head = (f"TKSfw briefing for {agent or 'this subagent'} from the project ledgers (`.agents/workarea/`). "
                "Respect decisions in force; report issues and results back in your END handoff and events; "
                "write ledger entries only in this session's shards.\n")
        return head + text
    except Exception as e:
        H.log(f"subagent_track: briefing: {type(e).__name__}: {e}")
        return ""


if __name__ == "__main__":
    main()
