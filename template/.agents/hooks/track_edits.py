#!/usr/bin/env python3
"""Edit tracker + ledger validator (PostToolUse / UserPromptSubmit) — harness-neutral.

Detects edits by HASHING the watched set (workarea ledgers, deliverables registered in
deliverables.yaml, framework files) before/after each tool call and journals the delta to
`.agents/workarea/.hook-state/journal.jsonl`. It never reads `tool_input.file_path` (Claude Code
only) or the transcript (unstable in both harnesses), so the same script behaves identically
under Codex CLI (`apply_patch`, shell writes, MCP tools) and Claude Code (`Edit`/`Write`, `Bash`,
MCP tools), and also sees writes made by subagents and by Python helpers.

Phases (`--phase`):
  tool    (default) PostToolUse. Journals the delta attributed to this tool call and, when a
          workarea YAML ledger changed, runs the yaml-log-entry validator on exactly those files.
          On a schema/parse failure it exits 2 with the report on stderr — both harnesses feed
          that back to the model as the tool result — so a malformed entry never silently
          persists. A delegation tool call (Agent/Task/spawn_agent) is journaled even when
          nothing changed, for the Stop-hook handoff rule.
  prompt  UserPromptSubmit. Edits found here happened BETWEEN turns (the operator editing in
          Obsidian/Finder, Box sync, …). They are journaled as `phase: prompt` so the Stop hook
          does not blame the agent for them, and the baseline is refreshed. Silent.

Exit codes: 0 silent (nothing to say, or an internal error — fail-open); 2 validation failure.
"""
import sys
sys.dont_write_bytecode = True
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hooklib as H  # noqa: E402


def validate(rel_paths):
    """Run the skill validator on each changed ledger; return the concatenated failure report
    ('' when all valid or the validator is missing)."""
    if not os.path.exists(H.VALIDATOR):
        return ""
    reports = []
    for rel in rel_paths:
        path = os.path.join(H.PROJECT_ROOT, rel)
        if not os.path.exists(path):
            continue                                   # deleted ledger: nothing to validate
        try:
            res = subprocess.run([sys.executable, H.VALIDATOR, path],
                                 capture_output=True, text=True, timeout=30)
        except Exception as e:                         # never wedge on a tooling error
            H.log(f"track_edits: validator error on {rel}: {e}")
            continue
        if res.returncode != 0:
            reports.append(f"[{rel}]\n{(res.stdout or '') + (res.stderr or '')}".rstrip())
    return "\n".join(reports)


def main():
    phase = "tool"
    if "--phase" in sys.argv:
        i = sys.argv.index("--phase")
        if i + 1 < len(sys.argv):
            phase = sys.argv[i + 1]
    payload = H.read_payload()
    tool_name = payload.get("tool_name") if phase == "tool" else None
    tool_use_id = payload.get("tool_use_id") if phase == "tool" else None

    try:
        with H.locked():
            changed, first_run = H.record_changes(payload, phase, tool_name, tool_use_id)
    except Exception as e:
        H.log(f"track_edits({phase}): {type(e).__name__}: {e}")
        sys.exit(0)

    if phase != "tool" or first_run:
        sys.exit(0)

    ledgers = [c["path"] for c in changed
               if (c.get("class") or "").startswith("ledger:") and c["kind"] != "deleted"]
    if not ledgers:
        sys.exit(0)
    report = validate(ledgers)
    if not report:
        sys.exit(0)
    sys.stderr.write(
        "Workarea YAML validation FAILED — fix the entry before continuing "
        "— load the yaml-log-entry skill: schemas in "
        f"{H.SCHEMAS_MD}, ID minting in {os.path.join(H.VALIDATOR_DIR, 'new_entry_id.py')}:\n"
        + report + "\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
