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


def validate_agents(rel_paths):
    """Run the define-agent validator on each changed agent definition; '' when clean/missing."""
    if not os.path.exists(H.AGENT_VALIDATOR):
        return ""
    reports = []
    for rel in rel_paths:
        path = os.path.join(H.PROJECT_ROOT, rel)
        if not os.path.exists(path):
            continue
        try:
            res = subprocess.run([sys.executable, H.AGENT_VALIDATOR, path, "--models", H.MODELS_TOML],
                                 capture_output=True, text=True, timeout=30)
        except Exception as e:
            H.log(f"track_edits: agent validator error on {rel}: {e}")
            continue
        if res.returncode == 2:
            reports.append(f"[{rel}]\n{(res.stdout or '') + (res.stderr or '')}".rstrip())
    return "\n".join(reports)


def render_mirrors(rel_paths):
    """Render the Codex/Claude mirrors of validated agent sources. Advisory: returns a message when
    something could not be rendered ('' otherwise) — the write already happened, never block."""
    try:
        import agentlib
        res = agentlib.sync(check=False, only=[os.path.join(H.PROJECT_ROOT, r) for r in rel_paths])
    except Exception as e:
        H.log(f"track_edits: agent mirror rendering: {type(e).__name__}: {e}")
        return ""
    bad = [r for r in res if r[0] == "conflict"]
    if bad:
        return ("Agent mirrors not rendered — fix and re-save the source (or run sync_harness.py --models): "
                + "; ".join(f"{r[1]}: {r[2] if len(r) > 2 else ''}" for r in bad))
    return ""


def prune_mirrors(rel_paths):
    try:
        import agentlib
        for r in rel_paths:
            agentlib.remove_mirrors(os.path.splitext(os.path.basename(r))[0], False, [])
    except Exception as e:
        H.log(f"track_edits: agent mirror pruning: {type(e).__name__}: {e}")


def main():
    phase = "tool"
    if "--phase" in sys.argv:
        i = sys.argv.index("--phase")
        if i + 1 < len(sys.argv):
            phase = sys.argv[i + 1]
    H.guard()
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
    agents = [c["path"] for c in changed
              if H.AGENT_FILE_RE.match(c["path"]) and c["kind"] != "deleted"]
    deleted_agents = [c["path"] for c in changed
                      if H.AGENT_FILE_RE.match(c["path"]) and c["kind"] == "deleted"]
    if deleted_agents:
        prune_mirrors(deleted_agents)
    if not ledgers and not agents:
        sys.exit(0)
    messages = []
    report = validate(ledgers) if ledgers else ""
    if report:
        messages.append(
            "Workarea YAML validation FAILED — fix the entry before continuing "
            "— load the yaml-log-entry skill: schemas in "
            f"{H.SCHEMAS_MD}, ID minting in {os.path.join(H.VALIDATOR_DIR, 'new_entry_id.py')}:\n" + report)
    areport = validate_agents(agents) if agents else ""
    if areport:
        messages.append(
            "Agent definition validation FAILED — fix the file before continuing — load the "
            f"define-agent skill (convention: {os.path.join(os.path.dirname(H.AGENT_VALIDATOR), '..', 'references', 'naming.md')}); "
            "the harness mirrors are rendered automatically once the file is valid; log the change in changes.yaml:\n" + areport)
    if not messages:
        advisory = render_mirrors(agents) if agents else ""
        if advisory:
            H.emit({"systemMessage": advisory})
        sys.exit(0)
    sys.stderr.write("\n".join(messages) + "\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
