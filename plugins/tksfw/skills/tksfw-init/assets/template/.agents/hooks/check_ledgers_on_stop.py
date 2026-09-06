#!/usr/bin/env python3
"""Stop hook: advisory ledger reminder at the end of a turn — harness-neutral.

Reads the edit JOURNAL written by `track_edits.py` (never the transcript) and applies the
order-based completeness rules of AGENTS.md for the current turn:
  * Un-logged CHANGE (deliverable) — a registry-matched deliverable changed AFTER the last
    write to `changes.yaml` (or with no such write).
  * Un-logged CHANGE (framework)   — `.agents/**`, `.codex/**`, `.claude/**` (minus the
    workarea) or a root instruction file changed after the last `changes.yaml` write.
  * Un-logged HANDOFF              — a subagent delegation (Agent / Task / spawn_agent) occurred
    after the last `handoffs.yaml` OR `events.yaml` write.
Edits journaled with `phase: prompt` (made between turns by the operator) are ignored.

MODE
  advisory (default)  emit a `systemMessage` (shown to the operator; never blocks).
  block               additionally return {"decision": "block", "reason": ...} ONCE per turn
                      (guarded by `stop_hook_active`), which both harnesses turn into a
                      continuation prompt so the model records the missing entries.
Set `LEDGER_STOP_MODE=block` in the environment to enable blocking.

The turn key is `turn_id` (Codex) or `prompt_id` (Claude Code); a `stop` marker is appended to
the journal so the fallback (same session, after last stop) also works. Fail-open throughout.
"""
import sys
sys.dont_write_bytecode = True
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402

MODE = os.environ.get("LEDGER_STOP_MODE", "advisory").strip().lower()


def main():
    H.guard()
    payload = H.read_payload()
    if payload.get("stop_hook_active"):
        sys.exit(0)                                    # never re-fire inside a continuation
    try:
        with H.locked():
            entries = H.read_journal()
            turn_entries = H.entries_for_turn(entries, payload)
            H.append_journal({"type": "stop", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                              "session_id": payload.get("session_id"),
                              "turn": H.turn_key(payload)})
        flags, paths = H.unlogged(turn_entries)
    except Exception as e:
        H.log(f"check_ledgers_on_stop: {type(e).__name__}: {e}")
        sys.exit(0)

    if not any(flags.values()):
        sys.exit(0)                                    # silent on clean turns

    items = []
    if flags["deliverable"]:
        items.append("• Deliverable edits without a later `changes.yaml` entry (Layer: PROJECT): "
                     + ", ".join(paths["deliverable"][:6])
                     + (" …" if len(paths["deliverable"]) > 6 else ""))
    if flags["framework"]:
        items.append("• Framework/method edits without a later `changes.yaml` entry "
                     "(Layer: METHOD or ARCHETYPE): "
                     + ", ".join(paths["framework"][:6])
                     + (" …" if len(paths["framework"]) > 6 else ""))
    if flags["handoff"]:
        items.append("• A subagent delegation without a matching `handoffs.yaml` (BEGIN/END) + "
                     "`events.yaml` entry.")
    msg = ("Ledger reminder — this turn ended with un-logged actions:\n" + "\n".join(items)
           + "\nAlso review whether a lesson belongs in `lessons.yaml`. Load the `yaml-log-entry` "
             f"skill before writing (schemas: `{H.SCHEMAS_MD}`). "
             f"Ledgers live in `{H.WORKAREA_REL}/`.")

    out = {"systemMessage": msg}
    if MODE == "block":
        out["decision"] = "block"
        out["reason"] = msg
    H.emit(out)
    sys.exit(0)


if __name__ == "__main__":
    main()
