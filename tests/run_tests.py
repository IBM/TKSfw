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
  7. Model routing: models.toml validates; route_model.py resolves Codex/Claude spawns (table
     selection by CODEX_HOME model_provider, ANTHROPIC_BASE_URL, TKSFW_ROUTING), denies unknown
     roles and missing tables, ignores non-spawn tools, works from the plugin bundle;
     sync_harness.py --models renders Codex agent TOML (inline/strip) and Claude mirrors
  8. tksfw-tools plugin: both manifests, mcp/*.json valid with the expected secret mechanism per
     harness, marketplaces list both plugins, check_tools.py silent/advisory
  9. define-agent: skill suite; track_edits.py blocks a non-conforming .codex/agents/*.toml (exit 2)
     and accepts a conforming one — then renders .codex/agents + .claude/agents mirrors (also from
     the plugin bundle); mirrors are unwatched; deleting the source prunes them; AGENTS.md kernel is
     harness-neutral
 10. Arming: plugin hooks are inert in a folder without .agents/.tksfw.json (nothing created), in a
     project disabled via the manifest, and yield in a full-mode project; legacy in-project layout
     without manifest stays armed; new_project --disable/--enable; version-skew warning
 11. tksfw-init: the plugin bundles SKILL.md + assets/{template,new_project.py,VERSION} and the
     bootstrap stanzas; a project can be created, disarmed and updated from the bundle alone
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
        check("skills bundled", skills == ["define-agent", "register-deliverables", "tksfw-init", "verify-integrity", "verify-sources", "yaml-log-entry"], str(skills))
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

        # 7 — model routing
        def hook(tool_name, tool_input, env=None, cwd=full, script=None, extra=None):
            payload = {"session_id": "s", "cwd": cwd, "hook_event_name": "PreToolUse",
                       "tool_name": tool_name, "tool_use_id": "u", "tool_input": tool_input}
            payload.update(extra or {})
            r = run([PY, script or os.path.join(full, ".agents", "hooks", "route_model.py")],
                    cwd=cwd, env=env, inp=json.dumps(payload))
            try:
                return r, (json.loads(r.stdout) if r.stdout.strip() else {})
            except Exception:
                return r, {"_raw": r.stdout}
        codex_home = os.path.join(tmp, "codexhome")
        os.makedirs(codex_home)
        with open(os.path.join(codex_home, "config.toml"), "w") as fh:
            fh.write('model = "gpt-5.6-sol"\nmodel_provider = "ibm"\n\n[model_providers.ibm]\nbase_url = "https://x"\n')
        base_env = {"CODEX_HOME": codex_home, "ANTHROPIC_BASE_URL": "", "TKSFW_ROUTING": ""}
        base_env = {k: v for k, v in base_env.items() if v} | {"CODEX_HOME": codex_home}
        rm = os.path.join(full, ".agents", "hooks", "route_model.py")
        r = run([PY, rm, "--check"], cwd=full, env=base_env)
        check("routing: models.toml --check", r.returncode == 0 and "ok" in r.stdout, r.stdout + r.stderr)
        r = run([PY, rm, "--print", "--codex"], cwd=full, env=base_env)
        check("routing: --print selects [routing.ibm] from CODEX_HOME", r.returncode == 0 and "routing='ibm'" in r.stdout, r.stdout)
        r, out = hook("spawn_agent", {"task_name": "sources-researcher_scan", "message": "m", "fork_turns": "none"},
                      env=base_env, extra={"turn_id": "t1"})
        hs = out.get("hookSpecificOutput", {})
        check("routing codex: researcher → luna/low via updatedInput",
              hs.get("permissionDecision") == "allow" and hs.get("updatedInput", {}).get("model") == "gpt-5.6-luna"
              and hs["updatedInput"].get("reasoning_effort") == "low" and hs["updatedInput"].get("task_name") == "sources-researcher_scan"
              and "gpt-5.6-luna" in hs.get("additionalContext", ""), r.stdout + r.stderr)
        r, out = hook("Agent", {"subagent_type": "report-builder", "prompt": "p", "description": "d"},
                      env=base_env | {"ANTHROPIC_BASE_URL": "https://openrouter.ai/api/v1"}, extra={"prompt_id": "p1"})
        hs = out.get("hookSpecificOutput", {})
        check("routing claude: builder → openrouter table by ANTHROPIC_BASE_URL, model only",
              hs.get("permissionDecision") == "allow" and hs.get("updatedInput", {}).get("model") == "openai/gpt-5.6-terra"
              and "reasoning_effort" not in hs.get("updatedInput", {}), r.stdout + r.stderr)
        r, out = hook("Agent", {"subagent_type": "x-planner", "prompt": "p"}, env=base_env, extra={"prompt_id": "p2"})
        hs = out.get("hookSpecificOutput", {})
        check("routing: TKSFW_ROUTING override", hook("Agent", {"subagent_type": "x-planner", "prompt": "p"},
              env=base_env | {"TKSFW_ROUTING": "openrouter"}, extra={"prompt_id": "p3"})[1]
              .get("hookSpecificOutput", {}).get("updatedInput", {}).get("model") == "anthropic/claude-opus-5")
        check("routing claude without base URL: falls back to codex provider? no — denied (no default table)",
              hs.get("permissionDecision") == "deny" and "no [routing.*] table" in hs.get("permissionDecisionReason", ""), r.stdout)
        r, out = hook("spawn_agent", {"agent_type": "atlas"}, env=base_env, extra={"turn_id": "t2"})
        hs = out.get("hookSpecificOutput", {})
        check("routing: unknown role denied", hs.get("permissionDecision") == "deny" and "atlas" in hs.get("permissionDecisionReason", ""), r.stdout)
        r, out = hook("Bash", {"command": "ls"}, env=base_env, extra={"turn_id": "t3"})
        check("routing: non-spawn tool untouched", r.returncode == 0 and out == {}, r.stdout + r.stderr)
        jl = os.path.join(full, ".agents", "workarea", ".hook-state", "routing.jsonl")
        check("routing: decisions journaled", os.path.isfile(jl) and sum(1 for _ in open(jl)) >= 4)
        # plugin bundle: hook runs from the plugin dir against the plugin-mode project (has models.toml)
        check("plugin-mode project carries models.toml", os.path.isfile(os.path.join(proj, ".agents", "models.toml")))
        r, out = hook("spawn_agent", {"agent_type": "output-validator"}, env=base_env | {"CLAUDE_PLUGIN_ROOT": plug},
                      cwd=proj, script=os.path.join(plug, "hooks", "route_model.py"), extra={"turn_id": "t4"})
        hs = out.get("hookSpecificOutput", {})
        check("routing from plugin bundle: validator → sol/high",
              hs.get("updatedInput", {}).get("model") == "gpt-5.6-sol" and hs["updatedInput"].get("reasoning_effort") == "high", r.stdout + r.stderr)
        # sync --models
        agents = os.path.join(full, ".agents", "agents")
        codex_mirrors = os.path.join(full, ".codex", "agents")
        with open(os.path.join(agents, "sources-researcher.toml"), "w") as fh:
            fh.write('name = "sources-researcher"\ndescription = "Use PROACTIVELY when sources are needed."\nmodel = "stale"\n'
                     'sandbox_mode = "read-only"\ndeveloper_instructions = """\nFind sources.\n"""\n')
        with open(os.path.join(agents, "final-writer.toml"), "w") as fh:
            fh.write('# tksfw-tier: judge\nname = "final-writer"\ndescription = "MUST BE USED for assembling the final report."\n'
                     'developer_instructions = "Assemble deliverables/report.md from validated inputs; success: all sections present."\n')
        sync = os.path.join(full, ".agents", "hooks", "sync_harness.py")
        r = run([PY, sync, "--models", "--check"], cwd=full, env=base_env)
        check("sync --models --check reports stale", r.returncode == 1 and "stale" in r.stdout, r.stdout + r.stderr)
        r = run([PY, sync, "--models"], cwd=full, env=base_env)
        t1 = open(os.path.join(codex_mirrors, "sources-researcher.toml")).read()
        t2 = open(os.path.join(codex_mirrors, "final-writer.toml")).read()
        src1 = open(os.path.join(agents, "sources-researcher.toml")).read()
        check("sync --models renders Codex mirrors (name role + tier comment overrides), source untouched",
              r.returncode == 0 and 'model = "gpt-5.6-luna"' in t1 and 'model_reasoning_effort = "low"' in t1
              and 'model = "gpt-5.6-sol"' in t2 and "Find sources." in t1 and t1.startswith("# tksfw:mirror")
              and 'model = "stale"' in src1, r.stdout + r.stderr + t1 + t2)
        md = os.path.join(full, ".claude", "agents", "sources-researcher.md")
        m = open(md).read() if os.path.isfile(md) else ""
        check("sync --models writes Claude mirror with model/effort/tools",
              "model: gpt-5.6-luna" in m and "effort: low" in m and "tools: Read" in m and "tksfw:mirror" in m and "Find sources." in m, m)
        r = run([PY, sync, "--models", "--check"], cwd=full, env=base_env)
        check("sync --models idempotent", r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stdout)
        with open(os.path.join(full, ".claude", "agents", "manual.md"), "w") as fh:
            fh.write("---\nname: manual\ndescription: x\n---\nhand made\n")
        r = run([PY, sync, "--models", "--routing", "openrouter"], cwd=full, env=base_env)
        t1 = open(os.path.join(codex_mirrors, "sources-researcher.toml")).read()
        check("sync --models --routing switches table", 'model = "google/gemini-3-flash"' in t1 and os.path.isfile(os.path.join(full, ".claude", "agents", "manual.md")), r.stdout + t1)
        mt = os.path.join(full, ".agents", "models.toml")
        mt_text = open(mt, encoding="utf-8").read().replace('codex_agent_files = "inline"', 'codex_agent_files = "strip"')
        with open(mt, "w", encoding="utf-8") as fh:
            fh.write(mt_text)
        r = run([PY, sync, "--models"], cwd=full, env=base_env)
        t1 = open(os.path.join(codex_mirrors, "sources-researcher.toml")).read()
        check("sync --models strip: Codex mirror has no model lines",
              "model" not in t1.replace("developer_instructions", "").replace("# tksfw:mirror", "") and "Find sources." in t1, t1)
        os.remove(os.path.join(agents, "final-writer.toml"))
        r = run([PY, sync, "--models"], cwd=full, env=base_env)
        check("sync --models removes orphan mirrors (both harnesses)",
              not os.path.exists(os.path.join(full, ".claude", "agents", "final-writer.md"))
              and not os.path.exists(os.path.join(codex_mirrors, "final-writer.toml")) and "removed" in r.stdout, r.stdout)

        # 9 — define-agent: skill suite, hook block on write, sync refuses invalid file
        r = run([PY, os.path.join(REPO, "template", ".agents", "skills", "define-agent", "tests", "run_tests.py")])
        check("define-agent suite", r.returncode == 0 and "cases passed" in r.stdout, r.stdout[-400:] + r.stderr[-300:])
        check("define-agent bundled in plugin with validator",
              os.path.isfile(os.path.join(plug, "skills", "define-agent", "assets", "validate_agent.py"))
              and os.path.isfile(os.path.join(plug, "skills", "define-agent", "references", "naming.md")))
        hooks_dir = os.path.join(full, ".agents", "hooks")
        sess = json.dumps({"session_id": "s9", "turn_id": "t9", "source": "startup", "cwd": full})
        run([PY, os.path.join(hooks_dir, "inject_state.py")], cwd=full, env=base_env, inp=sess)       # baseline
        with open(os.path.join(agents, "atlas.toml"), "w") as fh:
            fh.write('name = "atlas"\ndescription = "Use PROACTIVELY when anything."\ndeveloper_instructions = "do stuff"\n')
        post = json.dumps({"session_id": "s9", "turn_id": "t9", "hook_event_name": "PostToolUse", "tool_name": "apply_patch",
                           "tool_use_id": "u9", "cwd": full, "tool_input": {}})
        r = run([PY, os.path.join(hooks_dir, "track_edits.py")], cwd=full, env=base_env, inp=post)
        check("track_edits blocks a non-conforming agent file (exit 2, define-agent pointer)",
              r.returncode == 2 and "Agent definition validation FAILED" in r.stderr and "define-agent" in r.stderr
              and "not in the vocabulary" in r.stderr, f"rc={r.returncode} {r.stdout[-200:]} {r.stderr[-400:]}")
        r = run([PY, sync, "--models"], cwd=full, env=base_env)
        check("sync --models refuses to render an invalid agent file",
              r.returncode == 1 and "conflict" in r.stdout and "atlas" in r.stdout
              and not os.path.exists(os.path.join(full, ".claude", "agents", "atlas.md"))
              and not os.path.exists(os.path.join(codex_mirrors, "atlas.toml")), r.stdout)
        os.remove(os.path.join(agents, "atlas.toml"))
        with open(os.path.join(agents, "pricing-reviewer.toml"), "w") as fh:
            fh.write('name = "pricing-reviewer"\ndescription = "MUST BE USED for reviewing pricing tables."\nsandbox_mode = "read-only"\n'
                     'developer_instructions = "Review deliverables/pricing/*.md; return findings with acceptance criteria."\n')
        agents_md = open(os.path.join(full, "AGENTS.md"), encoding="utf-8").read()
        r = run([PY, os.path.join(hooks_dir, "track_edits.py")], cwd=full, env=base_env, inp=post)
        check("track_edits accepts a conforming agent file", r.returncode == 0, f"rc={r.returncode} {r.stderr[-400:]}")
        cm = os.path.join(codex_mirrors, "pricing-reviewer.toml")
        am = os.path.join(full, ".claude", "agents", "pricing-reviewer.md")
        check("track_edits renders both mirrors after a validated write",
              os.path.isfile(cm) and os.path.isfile(am) and open(cm).read().startswith("# tksfw:mirror")
              and 'model = ' not in open(cm).read()          # models.toml is in strip mode at this point
              and "model: gpt-5.6-sol" in open(am).read() and "tools: Read" in open(am).read(),
              f"cm={os.path.isfile(cm)} am={os.path.isfile(am)} out={r.stdout[-300:]} err={r.stderr[-300:]} ls={os.listdir(codex_mirrors) if os.path.isdir(codex_mirrors) else None}")
        probe3 = ("import sys; sys.path.insert(0, %r); import hooklib as H; "
                  "print(H.classify('.codex/agents/pricing-reviewer.toml'), H.classify('.claude/agents/pricing-reviewer.md'), "
                  "H.classify('.agents/agents/pricing-reviewer.toml'))") % hooks_dir
        r = run([PY, "-c", probe3], cwd=full, env=base_env)
        check("mirrors are not watched; the source is a framework edit", r.stdout.strip() == "None None framework", r.stdout + r.stderr)
        os.remove(os.path.join(agents, "pricing-reviewer.toml"))
        r = run([PY, os.path.join(hooks_dir, "track_edits.py")], cwd=full, env=base_env, inp=post)
        check("deleting the source prunes both mirrors", r.returncode == 0 and not os.path.exists(cm) and not os.path.exists(am), r.stdout + r.stderr)
        # plugin mode: the hook bundle renders mirrors into the plugin-mode project
        os.makedirs(os.path.join(proj, ".agents", "agents"), exist_ok=True)
        penv = base_env | {"CLAUDE_PLUGIN_ROOT": plug}
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=proj, env=penv,
            inp=json.dumps({"session_id": "p9", "turn_id": "t", "source": "startup", "cwd": proj}))
        with open(os.path.join(proj, ".agents", "agents", "data-fetcher.toml"), "w") as fh:
            fh.write('name = "data-fetcher"\ndescription = "Use PROACTIVELY when raw data files must be fetched."\nsandbox_mode = "workspace-write"\n'
                     'developer_instructions = "Fetch inputs into .agents/workarea/data-fetcher/; success: files listed with checksums; return a table."\n')
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=proj, env=penv,
                inp=json.dumps({"session_id": "p9", "turn_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "u", "cwd": proj, "tool_input": {}}))
        pcm = os.path.join(proj, ".codex", "agents", "data-fetcher.toml")
        check("plugin mode: hook renders agent mirrors into the project",
              r.returncode == 0 and os.path.isfile(pcm) and 'model = "gpt-5.6-luna"' in open(pcm).read()   # fetcher → research tier
              and os.path.isfile(os.path.join(proj, ".claude", "agents", "data-fetcher.md")),
              f"rc={r.returncode} exists={os.path.isfile(pcm)} content={open(pcm).read()[:300] if os.path.isfile(pcm) else ''} out={r.stdout[-300:]} err={r.stderr[-300:]} "
              f"log={open(os.path.join(proj, '.agents', 'workarea', '.hook-state', 'hooks.log')).read()[-500:] if os.path.isfile(os.path.join(proj, '.agents', 'workarea', '.hook-state', 'hooks.log')) else ''}")
        check("AGENTS.md names no harness directory",
              ".codex/agents" not in agents_md and "Codex sessions" not in agents_md and ".agents/agents/" in agents_md)
        # 10 — arming guard
        junk = os.path.join(tmp, "junk", "deeper")
        os.makedirs(junk)
        penv = base_env | {"CLAUDE_PLUGIN_ROOT": plug}
        for script, inp in (("inject_state.py", {"session_id": "j", "turn_id": "t", "source": "startup", "cwd": junk}),
                            ("track_edits.py", {"session_id": "j", "turn_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "u", "cwd": junk, "tool_input": {}}),
                            ("check_ledgers_on_stop.py", {"session_id": "j", "turn_id": "t", "hook_event_name": "Stop", "cwd": junk}),
                            ("refresh_state.py", {"session_id": "j", "turn_id": "t", "cwd": junk}),
                            ("route_model.py", {"session_id": "j", "turn_id": "t", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "x-planner"}, "cwd": junk})):
            r = run([PY, os.path.join(plug, "hooks", script)], cwd=junk, env=penv, inp=json.dumps(inp))
            check(f"unarmed folder: {script} exits 0 silently", r.returncode == 0 and r.stdout.strip() == "" and r.stderr.strip() == "", r.stdout + r.stderr)
        check("unarmed folder: nothing was created", sorted(os.listdir(junk)) == [] and sorted(os.listdir(os.path.dirname(junk))) == ["deeper"])
        # disarm the plugin-mode project
        r = run([PY, os.path.join(work, "tools", "new_project.py"), proj, "--disable"])
        check("new_project.py --disable writes enabled=false", r.returncode == 0 and json.load(open(os.path.join(proj, ".agents", ".tksfw.json")))["enabled"] is False, r.stdout + r.stderr)
        shutil.rmtree(os.path.join(proj, ".agents", "workarea", ".hook-state"), ignore_errors=True)
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=proj, env=penv,
                inp=json.dumps({"session_id": "d", "turn_id": "t", "source": "startup", "cwd": proj}))
        r2 = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=proj, env=penv,
                 inp=json.dumps({"session_id": "d", "turn_id": "t", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "x-planner"}, "cwd": proj}))
        check("disabled project: hooks inert, no state written, no routing",
              r.returncode == 0 and r.stdout.strip() == "" and r2.stdout.strip() == ""
              and not os.path.exists(os.path.join(proj, ".agents", "workarea", ".hook-state")), r.stdout + r2.stdout)
        r = run([PY, os.path.join(work, "tools", "new_project.py"), proj, "--enable"])
        r2 = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=proj, env=penv,
                 inp=json.dumps({"session_id": "d", "turn_id": "t", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "x-planner"}, "cwd": proj}))
        check("re-enabled project: routing active again", r.returncode == 0 and '"model": "gpt-5.6-sol"' in r2.stdout, r.stdout + r2.stdout)
        # yield: plugin instance in a full-mode project
        probe = ("import sys; sys.path.insert(0, %r); import hooklib as H; print(H.armed())")
        r = run([PY, "-c", probe % os.path.join(plug, "hooks")], cwd=full, env=penv)
        r2 = run([PY, "-c", probe % os.path.join(full, ".agents", "hooks")], cwd=full, env=base_env)
        check("full-mode project: plugin instance yields, in-project instance armed",
              "yield" in r.stdout and r2.stdout.startswith("(True"), r.stdout + r2.stdout)
        mpath = os.path.join(full, ".agents", ".tksfw.json")
        os.rename(mpath, mpath + ".bak")
        r = run([PY, "-c", probe % os.path.join(full, ".agents", "hooks")], cwd=full, env=base_env)
        check("legacy in-project layout without manifest stays armed", r.stdout.startswith("(True") and "legacy" in r.stdout, r.stdout)
        os.rename(mpath + ".bak", mpath)
        # version skew warning
        m = json.load(open(os.path.join(proj, ".agents", ".tksfw.json")))
        m["version"] = "0.1.0"
        json.dump(m, open(os.path.join(proj, ".agents", ".tksfw.json"), "w"))
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=proj, env=penv,
                inp=json.dumps({"session_id": "v", "turn_id": "t", "source": "startup", "cwd": proj}))
        check("version skew is reported at SessionStart", "version skew" in r.stdout and "0.1.0" in r.stdout, r.stdout[:300])

        # 11 — tksfw-init from the plugin bundle
        init = os.path.join(plug, "skills", "tksfw-init")
        check("tksfw-init skill bundled with template, installer and VERSION",
              os.path.isfile(os.path.join(init, "SKILL.md")) and os.path.isfile(os.path.join(init, "assets", "new_project.py"))
              and os.path.isfile(os.path.join(init, "assets", "template", "AGENTS.md"))
              and os.path.isfile(os.path.join(init, "assets", "template", ".agents", "models.toml"))
              and open(os.path.join(init, "assets", "VERSION")).read().strip() == open(os.path.join(REPO, "VERSION")).read().strip()
              and not os.path.exists(os.path.join(init, "assets", "template", ".agents", "skills", "yaml-log-entry", "tests")))
        check("bootstrap stanzas bundled",
              all(os.path.isfile(os.path.join(plug, "bootstrap", f)) for f in ("AGENTS.global.md", "CLAUDE.global.md"))
              and ".agents/.tksfw.json" in open(os.path.join(plug, "bootstrap", "AGENTS.global.md")).read())
        np2 = os.path.join(tmp, "from-plugin")
        r = run([PY, os.path.join(init, "assets", "new_project.py"), np2, "--plugin-mode"])
        mf = os.path.join(np2, ".agents", ".tksfw.json")
        check("project created from the plugin bundle (plugin mode, armed)",
              r.returncode == 0 and os.path.isfile(os.path.join(np2, "AGENTS.md")) and os.path.isfile(mf)
              and json.load(open(mf))["enabled"] is True and json.load(open(mf))["version"] == open(os.path.join(REPO, "VERSION")).read().strip()
              and not os.path.exists(os.path.join(np2, ".agents", "hooks")), r.stdout + r.stderr)
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=np2, env=penv,
                inp=json.dumps({"session_id": "n", "turn_id": "t", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "sources-researcher"}, "cwd": np2}))
        check("plugin hooks serve the bundle-created project", '"model": "gpt-5.6-luna"' in r.stdout, r.stdout + r.stderr)
        r = run([PY, os.path.join(init, "assets", "new_project.py"), np2, "--disable"])
        r2 = run([PY, os.path.join(init, "assets", "new_project.py"), np2, "--update"])
        check("bundle installer: --disable then --update keeps enabled=false",
              r.returncode == 0 and r2.returncode == 0 and json.load(open(mf))["enabled"] is False, r.stdout + r2.stdout + r2.stderr)
        np3 = os.path.join(tmp, "from-plugin-full")
        r = run([PY, os.path.join(init, "assets", "new_project.py"), np3, "--no-sync"])
        check("bundle installer: self-contained project carries hooks and skills",
              r.returncode == 0 and os.path.isfile(os.path.join(np3, ".agents", "hooks", "hooks.json"))
              and os.path.isfile(os.path.join(np3, ".agents", "skills", "define-agent", "SKILL.md")), r.stdout + r.stderr)

        agents_md = open(os.path.join(full, "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md keeps the naming kernel and points to define-agent",
              "define-agent" in agents_md and "Reserved name `main`" in agents_md and "project-agent-1" not in agents_md
              and len(agents_md.encode()) < 19000)

        # 8 — tksfw-tools
        tools = os.path.join(work, "plugins", "tksfw-tools")
        for m in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            pth = os.path.join(tools, m)
            ok = os.path.isfile(pth)
            if ok:
                d = json.load(open(pth, encoding="utf-8"))
                ok = d["name"] == "tksfw-tools" and d["version"] == open(os.path.join(REPO, "VERSION")).read().strip() \
                    and d["mcpServers"].startswith("./mcp/") and os.path.isfile(os.path.join(tools, d["mcpServers"])) \
                    and d["hooks"] == "./hooks/hooks.json"
            check(f"tools manifest {m}", ok)
        cj = json.load(open(os.path.join(tools, "mcp", "codex.json"), encoding="utf-8"))
        check("tools codex.json: perplexity via env_vars whitelist, no literal key",
              cj["perplexity"]["env_vars"] == ["PERPLEXITY_API_KEY"] and "env" not in cj["perplexity"]
              and "--isolated" in cj["playwright"]["args"] and cj["playwright"]["startup_timeout_sec"] >= 60)
        aj = json.load(open(os.path.join(tools, "mcp", "claude.json"), encoding="utf-8"))["mcpServers"]
        check("tools claude.json: key from user_config, output dir under CLAUDE_PROJECT_DIR",
              aj["perplexity"]["env"]["PERPLEXITY_API_KEY"] == "${user_config.perplexity_api_key}"
              and any("${CLAUDE_PROJECT_DIR}/.playwright" == a for a in aj["playwright"]["args"]))
        uc = json.load(open(os.path.join(tools, ".claude-plugin", "plugin.json")))["userConfig"]["perplexity_api_key"]
        check("tools userConfig marks the key sensitive", uc.get("sensitive") is True)
        for mp in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
            names = [p["name"] for p in json.load(open(os.path.join(REPO, mp)))["plugins"]]
            check(f"marketplace {mp} lists both plugins", names == ["tksfw", "tksfw-tools"], str(names))
        ct = os.path.join(tools, "hooks", "check_tools.py")
        r = run([PY, ct], cwd=proj, env={"PATH": "/nonexistent", "PERPLEXITY_API_KEY": ""} | {"CLAUDE_PLUGIN_ROOT": tools},
                inp=json.dumps({"session_id": "s", "turn_id": "t", "source": "startup", "cwd": proj}))
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        check("check_tools.py reports missing npx and key (advisory, exit 0)",
              r.returncode == 0 and "npx" in ctx and "PERPLEXITY_API_KEY" in ctx and os.path.isdir(os.path.join(proj, ".playwright")), r.stdout + r.stderr)
        r = run([PY, ct], cwd=proj, env={"PERPLEXITY_API_KEY": "x", "PLAYWRIGHT_BROWSERS_PATH": os.path.join(tmp, "pw")},
                inp=json.dumps({"session_id": "s", "prompt_id": "p", "source": "startup", "cwd": proj}))
        os.makedirs(os.path.join(tmp, "pw", "chromium-1"), exist_ok=True)
        r2 = run([PY, ct], cwd=proj, env={"PERPLEXITY_API_KEY": "x", "PLAYWRIGHT_BROWSERS_PATH": os.path.join(tmp, "pw")},
                 inp=json.dumps({"session_id": "s", "prompt_id": "p", "source": "startup", "cwd": proj}))
        check("check_tools.py: browsers missing → warning; all present → silent",
              "Playwright browser" in r.stdout and r2.returncode == 0 and r2.stdout.strip() == "", r.stdout + "|" + r2.stdout)

    # 6 — committed plugin copy is current
    r = run([PY, os.path.join(REPO, "tools", "build_plugin.py"), "--check"])
    check("plugins/* committed copies are up to date", r.returncode == 0, r.stdout)

    print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
