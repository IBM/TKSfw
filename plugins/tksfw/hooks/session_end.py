#!/usr/bin/env python3
"""SessionEnd hook (3.5.0): mark this session's record as ended so it stops counting as active at once
(instead of after the 30-minute heartbeat window), and clear its live-subagent set. Both harnesses emit
SessionEnd for the main thread (Codex: on close/archive/idle 30 min; Claude Code: clear/resume/logout/exit).
Fail-open, exit 0 always. Never blocks."""
import sys
sys.dont_write_bytecode = True
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    try:
        if not H.armed()[0]:
            sys.exit(0)
        tok = H.end_session(payload, payload.get("reason") or "other")
        if tok:
            try:
                import subagent_track
                subagent_track.clear(tok)
            except Exception as e:
                H.log(f"session_end: live set: {e}")
            H.log(f"session_end: {tok} ended ({payload.get('reason') or 'other'})")
    except Exception as e:
        H.log(f"session_end: {type(e).__name__}: {e}")
    sys.exit(0)


if __name__ == "__main__":
    main()
