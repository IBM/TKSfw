#!/usr/bin/env python3
"""TKSfw test runner (standard library only).

  1. yaml-log-entry skill suite (template/.agents/skills/yaml-log-entry/tests/run_tests.py)
  2. Plugin build into a temp dir: manifests valid, ./-relative paths, every hook script present,
     no `.agents/hooks/` command left, skills namespace complete
  3. Hook scripts in PLUGIN mode: cwd = a scratch project, scripts run from the built plugin
     directory (CLAUDE_PLUGIN_ROOT set, CLAUDE_PROJECT_DIR unset) — refresh_state.py --print must
     succeed and write STATE.md into the *project* workarea, not into the plugin
  4. Same scripts in IN-PROJECT mode (legacy layout) from a different cwd — still resolve the root
  5. new_project.py: full + plugin-mode instantiation into temp dirs, --update keeps a local edit
  6. plugins/tksfw/ committed copy is up to date with the template (build --check)
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import shutil
import subprocess
import tempfile

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
FAILS = []


def check(name, cond, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def run(cmd, cwd=None, env=None, inp=None):
    e = os.environ.copy()
    e.pop("CLAUDE_PROJECT_DIR", None)
    e.pop("TKSFW_PROJECT_ROOT", None)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, input=inp, capture_output=True, text=True, timeout=120)


def main():
    # 1 — skill suite
    r = run([PY, os.path.join(REPO, "template", ".agents", "skills", "yaml-log-entry", "tests", "run_tests.py")])
    check("yaml-log-entry suite", r.returncode == 0 and "cases passed" in r.stdout, r.stdout[-300:] + r.stderr[-300:])

    with tempfile.TemporaryDirectory() as tmp:
        # 2 — build into temp (use the real builder but redirect output via a symlinked repo copy)
        work = os.path.join(tmp, "repo")
        shutil.copytree(REPO, work, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__", "plugins"))
        r = run([PY, os.path.join(work, "tools", "build_plugin.py"), "--no-zip"])
        check("build_plugin.py runs", r.returncode == 0, r.stdout + r.stderr)
        plug = os.path.join(work, "plugins", "tksfw")
        for m in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            p = os.path.join(plug, m)
            ok = os.path.isfile(p)
            if ok:
                d = json.load(open(p, encoding="utf-8"))
                ok = d["name"] == "tksfw" and d["skills"] == "./skills/" and d["hooks"] == "./hooks/hooks.json" \
                    and d["version"] == open(os.path.join(REPO, "VERSION")).read().strip()
            check(f"manifest {m}", ok)
        hooks = json.load(open(os.path.join(plug, "hooks", "hooks.json"), encoding="utf-8"))
        cmds = [h["command"] for gs in hooks["hooks"].values() for g in gs for h in g["hooks"]]
        check("hook commands rewritten to ${CLAUDE_PLUGIN_ROOT}",
              cmds and all('"${CLAUDE_PLUGIN_ROOT}/hooks/' in c and ".agents/hooks" not in c for c in cmds), str(cmds))
        check("sync_harness.py excluded from plugin", not os.path.exists(os.path.join(plug, "hooks", "sync_harness.py")))
        skills = sorted(os.listdir(os.path.join(plug, "skills")))
        check("skills bundled", skills == ["register-deliverables", "verify-integrity", "verify-sources", "yaml-log-entry"], str(skills))
        check("skill tests dropped from bundle", not os.path.exists(os.path.join(plug, "skills", "yaml-log-entry", "tests")))
        check("validator present in bundle", os.path.isfile(os.path.join(plug, "skills", "yaml-log-entry", "assets", "validate_yaml_log.py")))

        # 3 — plugin mode: scratch project with only the method instance
        proj = os.path.join(tmp, "proj")
        r = run([PY, os.path.join(work, "tools", "new_project.py"), proj, "--plugin-mode"])
        check("new_project.py --plugin-mode", r.returncode == 0, r.stdout + r.stderr)
        check("plugin-mode project has no .agents/hooks", not os.path.exists(os.path.join(proj, ".agents", "hooks")))
        check("plugin-mode project has AGENTS.md + workarea",
              os.path.isfile(os.path.join(proj, "AGENTS.md")) and os.path.isdir(os.path.join(proj, ".agents", "workarea")))
        env = {"CLAUDE_PLUGIN_ROOT": plug}
        sub = os.path.join(proj, "some", "nested", "dir")
        os.makedirs(sub)
        # root resolution probe (import hooklib from the plugin, cwd nested inside the project)
        probe = ("import sys; sys.path.insert(0, %r); import hooklib as H; "
                 "print(H.PROJECT_ROOT); print(H.VALIDATOR_DIR); print(H.PLUGIN_MODE)") % os.path.join(plug, "hooks")
        r = run([PY, "-c", probe], cwd=sub, env=env)
        lines = r.stdout.strip().splitlines()
        check("plugin mode: project root resolved by walking up from cwd",
              r.returncode == 0 and len(lines) == 3 and os.path.realpath(lines[0]) == os.path.realpath(proj), r.stdout + r.stderr)
        check("plugin mode: validator resolved inside the plugin",
              len(lines) == 3 and lines[1].startswith(plug) and lines[2] == "True", r.stdout)
        r = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=proj, env=env)
        check("plugin mode: refresh_state.py --print", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
        check("plugin mode: STATE.md written into the project workarea",
              os.path.isfile(os.path.join(proj, ".agents", "workarea", "STATE.md")))
        check("plugin mode: nothing written into the plugin dir",
              not os.path.exists(os.path.join(plug, ".agents")) and not any(
                  f.endswith((".log", ".jsonl")) for f in os.listdir(os.path.join(plug, "hooks"))))
        payload = json.dumps({"session_id": "t", "cwd": proj, "hook_event_name": "SessionStart", "source": "startup", "turn_id": "x"})
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=proj, env=env, inp=payload)
        ok = r.returncode == 0
        if ok and r.stdout.strip():
            try:
                out = json.loads(r.stdout)
                ok = "hookSpecificOutput" in out
            except Exception:
                ok = False
        check("plugin mode: inject_state.py emits hook JSON", ok, r.stdout[-200:] + r.stderr[-200:])
        # CLAUDE_PROJECT_DIR override wins even from an unrelated cwd
        r = run([PY, "-c", probe], cwd=tmp, env={"CLAUDE_PLUGIN_ROOT": plug, "CLAUDE_PROJECT_DIR": proj})
        check("plugin mode: CLAUDE_PROJECT_DIR honoured", r.returncode == 0 and os.path.realpath(r.stdout.splitlines()[0]) == os.path.realpath(proj), r.stdout + r.stderr)

        # 4 — in-project (full) mode from a foreign cwd
        full = os.path.join(tmp, "full")
        r = run([PY, os.path.join(work, "tools", "new_project.py"), full, "--no-sync"])
        check("new_project.py full mode", r.returncode == 0, r.stdout + r.stderr)
        probe2 = ("import sys; sys.path.insert(0, %r); import hooklib as H; print(H.PROJECT_ROOT); print(H.PLUGIN_MODE)") \
            % os.path.join(full, ".agents", "hooks")
        r = run([PY, "-c", probe2], cwd=tmp)
        ls = r.stdout.strip().splitlines()
        check("in-project mode: legacy root resolution from foreign cwd",
              r.returncode == 0 and len(ls) == 2 and os.path.realpath(ls[0]) == os.path.realpath(full) and ls[1] == "False", r.stdout + r.stderr)
        r = run([PY, os.path.join(full, ".agents", "hooks", "sync_harness.py"), "--mode", "link"], cwd=full)
        check("in-project mode: sync_harness.py", r.returncode == 0 and os.path.isfile(os.path.join(full, ".codex", "hooks.json"))
              and os.path.isfile(os.path.join(full, ".claude", "settings.json")), r.stdout[-300:] + r.stderr[-300:])

        # 5 — update semantics
        agents_md = os.path.join(full, "AGENTS.md")
        with open(agents_md, "a", encoding="utf-8") as fh:
            fh.write("\n<!-- local L3 rule -->\n")
        r = run([PY, os.path.join(work, "tools", "new_project.py"), full, "--update", "--no-sync"])
        check("new_project.py --update keeps local edits",
              r.returncode == 0 and "kept (edited locally)" in r.stdout and "local L3 rule" in open(agents_md, encoding="utf-8").read(), r.stdout + r.stderr)
        r = run([PY, os.path.join(work, "tools", "new_project.py"), full, "--no-sync"])
        check("new_project.py refuses re-install without --update", r.returncode != 0)

    # 6 — committed plugin copy is current
    r = run([PY, os.path.join(REPO, "tools", "build_plugin.py"), "--check"])
    check("plugins/tksfw committed copy is up to date", r.returncode == 0, r.stdout)

    print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
