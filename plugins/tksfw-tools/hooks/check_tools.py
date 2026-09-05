#!/usr/bin/env python3
"""SessionStart hook (tksfw-tools): report missing prerequisites of the bundled MCP servers.

Advisory only. Emits `hookSpecificOutput.additionalContext` listing what is missing; silent when
everything is present. Standard library only, fail-open (exit 0 always, no output on error).

Checks
  npx            on PATH (both servers are started with `npx -y …`)
  Playwright     a browser under the Playwright cache (macOS ~/Library/Caches/ms-playwright,
                 Linux ~/.cache/ms-playwright, Windows %LOCALAPPDATA%\\ms-playwright, or
                 $PLAYWRIGHT_BROWSERS_PATH) — otherwise `npx playwright install chromium`
  Perplexity key Codex: $PERPLEXITY_API_KEY in the shell (whitelisted via env_vars);
                 Claude Code: the plugin option, exported to hooks as
                 $CLAUDE_PLUGIN_OPTION_PERPLEXITY_API_KEY
  .playwright/   the project output directory the servers write to (created if missing, so the
                 first screenshot never fails on a missing folder)

Standalone:  python3 check_tools.py --print
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import shutil
import platform


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def harness(payload):
    if "turn_id" in payload or "model" in payload:
        return "codex"
    if "prompt_id" in payload or "effort" in payload or payload.get("permission_mode"):
        return "claude"
    return "unknown"


def playwright_browsers_present():
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):        # Playwright honours only this when set
        cands = [os.environ["PLAYWRIGHT_BROWSERS_PATH"]]
    else:
        home = os.path.expanduser("~")
        sysname = platform.system()
        if sysname == "Darwin":
            cands = [os.path.join(home, "Library", "Caches", "ms-playwright")]
        elif sysname == "Windows":
            cands = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")]
        else:
            cands = [os.path.join(home, ".cache", "ms-playwright")]
    for c in cands:
        try:
            if c and os.path.isdir(c) and any(e.startswith(("chromium", "chrome", "firefox", "webkit"))
                                             for e in os.listdir(c)):
                return True
        except Exception:
            continue
    return False


def project_dir(payload):
    for var in ("CLAUDE_PROJECT_DIR",):
        if os.environ.get(var):
            return os.environ[var]
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()


def problems(payload):
    out = []
    h = harness(payload)
    if not shutil.which("npx"):
        out.append("`npx` not on PATH — install Node.js (both bundled MCP servers start with `npx -y …`).")
    if not playwright_browsers_present():
        out.append("No Playwright browser found — run `npx playwright install chromium` once.")
    have_key = bool(os.environ.get("PERPLEXITY_API_KEY")) or bool(os.environ.get("CLAUDE_PLUGIN_OPTION_PERPLEXITY_API_KEY"))
    if not have_key:
        if h == "claude":
            out.append("Perplexity API key not configured — `/plugin` → tksfw-tools → configure `perplexity_api_key`.")
        else:
            out.append("`PERPLEXITY_API_KEY` is not set in this shell — the perplexity MCP server will fail to authenticate.")
    pd = project_dir(payload)
    try:
        os.makedirs(os.path.join(pd, ".playwright"), exist_ok=True)
    except Exception:
        out.append(f"Cannot create `{os.path.join(pd, '.playwright')}` (Playwright output directory).")
    return out


def main():
    if "--print" in sys.argv:
        ps = problems({})
        print("\n".join(ps) if ps else "tksfw-tools: all prerequisites present")
        sys.exit(1 if ps else 0)
    payload = read_payload()
    ps = problems(payload)
    if ps:
        text = ("tksfw-tools prerequisites missing (MCP servers perplexity/playwright may be unavailable):\n- "
                + "\n- ".join(ps))
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                             "additionalContext": text}}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
