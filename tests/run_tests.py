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
 12. delegate-work: skill tests; routing hook refuses nested spawns and the (N+1)th live subagent;
     SubagentStart/Stop tracking; main Stop clears the live set and reports stale work areas;
     AGENTS.md points to the skill; .agents/worktrees/ is never watched
 13. Activity plan: tasks_lint severity split; the PostToolUse hook blocks malformed tasks.md writes
     (exit 2) and only advises on missing evidence; tasks-archive.md is not linted; AGENTS.md keeps
     the five rules and points to yaml-log-entry/references/tasks.md; STATE.md archive hint
 14. Parallel sessions (1.4.0): session token + operator injected at SessionStart, other-session
     warning; owner fields required on new entries; lost-update guard (append-only removal, foreign
     removal in decisions, own removal allowed, TaskID removal vs archive move, A-B-A rewrite);
     per-session attribution (external ledger entry, ambiguous unnamed edit); per-session live cap;
     work areas keyed <session>.<task>.<n>
 15. Operator configuration item: ~/.config/tksfw/user.toml via --set-operator / --show-operator;
     resolution order env > file > git, reported source; SessionStart names the source
 16. ks + archives (1.5.0): ks bundled in plugins/tksfw/bin and self-locating; self/operator/project/
     routing/ledger/harness/doctor/dev sub-commands; `routing use` pins `selected`; cumulative archives
     under workarea/archive/ — archive_ledger.py moves closed history, the guard exempts the move and
     protects archives, cross_check resolves into archives, find_entry finds and cross-references
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import shutil
import re
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
        check("skills bundled", skills == ["define-agent", "delegate-work", "register-deliverables", "tksfw-init", "verify-integrity", "verify-sources", "yaml-log-entry"], str(skills))
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

        # 12 — delegate-work + delegation enforcement
        r = run([PY, os.path.join(REPO, "template", ".agents", "skills", "delegate-work", "tests", "run_tests.py")])
        check("delegate-work skill tests pass", r.returncode == 0 and "ALL PASSED" in r.stdout, r.stdout[-400:] + r.stderr[-400:])
        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md keeps the decision rules and points to delegate-work",
              "delegate-work" in agents_md and "NEVER run more than 4 parallel agents" in agents_md
              and "cannot spawn further subagents" in agents_md and "Use git worktrees for stricter isolation" not in agents_md
              and "sync_harness.py --models" not in agents_md)
        hooks_json = json.load(open(os.path.join(plug, "hooks", "hooks.json")))
        check("SubagentStart/SubagentStop hooks bundled and rewritten",
              all(ev in hooks_json["hooks"] for ev in ("SubagentStart", "SubagentStop"))
              and "${CLAUDE_PLUGIN_ROOT}/hooks/subagent_track.py" in hooks_json["hooks"]["SubagentStart"][0]["hooks"][0]["command"])
        # nested spawn denied
        dproj = os.path.join(tmp, "deleg")
        run([PY, os.path.join(work, "tools", "new_project.py"), dproj, "--plugin-mode"])
        spawn = lambda extra={}: json.dumps({"session_id": "d", "turn_id": "t9", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent",
                                              "tool_input": {"agent_type": "sources-researcher"}, "cwd": dproj, **extra})
        rm = lambda inp: run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=dproj, env=penv, inp=inp)
        check("spawn from a subagent context is denied (agent_id)", '"deny"' in rm(spawn({"agent_id": "sub1", "agent_type": "x-builder"})).stdout and "nested" in rm(spawn({"agent_id": "sub1"})).stdout.lower() or "cannot spawn" in rm(spawn({"agent_id": "sub1"})).stdout)
        check("spawn from a subagent context is denied (agent_path depth)", "cannot spawn" in rm(spawn({"agent_path": "/root/explorer"})).stdout)
        check("main-session spawn still allowed", '"allow"' in rm(spawn()).stdout)
        # parallel cap
        for i in range(4):
            run([PY, os.path.join(plug, "hooks", "subagent_track.py"), "--start"], cwd=dproj, env=penv,
                inp=json.dumps({"session_id": "d", "turn_id": "t9", "hook_event_name": "SubagentStart", "agent_id": f"a{i}", "agent_type": "x-builder", "cwd": dproj}))
        live = json.load(open(os.path.join(dproj, ".agents", "workarea", ".hook-state", "subagents.json")))["live"]
        check("SubagentStart tracked", len(live) == 4)
        r = rm(spawn())
        check("5th concurrent spawn denied", '"deny"' in r.stdout and "4 subagents are already running" in r.stdout, r.stdout[:300])
        run([PY, os.path.join(plug, "hooks", "subagent_track.py"), "--stop"], cwd=dproj, env=penv,
            inp=json.dumps({"session_id": "d", "turn_id": "t9", "hook_event_name": "SubagentStop", "agent_id": "a1", "cwd": dproj}))
        check("after one SubagentStop the spawn is allowed again", '"allow"' in rm(spawn()).stdout)
        # main Stop clears + stale advisory
        os.makedirs(os.path.join(dproj, ".agents", "workarea", "x-builder", "T001"))
        open(os.path.join(dproj, ".agents", "workarea", "tasks.md"), "w").write("# plan\n- [x] T001 done - main : COMPLETED 2026-09-06 10:00:00 [ev:abc12345]\n")
        r = run([PY, os.path.join(plug, "hooks", "check_ledgers_on_stop.py")], cwd=dproj, env=penv,
                inp=json.dumps({"session_id": "d", "turn_id": "t9", "hook_event_name": "Stop", "cwd": dproj}))
        live = json.load(open(os.path.join(dproj, ".agents", "workarea", ".hook-state", "subagents.json")))["live"]
        check("main Stop clears the live set and reports the stale work area",
              live == {} and "x-builder/T001" in r.stdout and "prune --stale" in r.stdout, r.stdout[:300])
        # worktrees never watched
        probe = "import sys; sys.path.insert(0, %r); import hooklib as H; print(H.classify('.agents/worktrees/x-builder--T1/AGENTS.md'))"
        r = run([PY, "-c", probe % os.path.join(plug, "hooks")], cwd=dproj, env=penv)
        check(".agents/worktrees/ is not a watched path", r.stdout.strip() == "None", r.stdout)

        # 13 — activity plan enforcement
        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md § Activity Plan reduced to rules + pointer",
              "references/tasks.md" in agents_md and "TaskIDs are random base62" in agents_md
              and "`update_plan`" in agents_md and "[ev:<EventID>]" in agents_md
              and "Terminal-positive EventType/Status pairs are" not in agents_md
              and "```markdown\n- [ ] <TaskID>" not in agents_md)
        ref = os.path.join(plug, "skills", "yaml-log-entry", "references", "tasks.md")
        check("tasks.md reference bundled with grammar and pairs table",
              os.path.isfile(ref) and "`REVIEW` | `PASS`" in open(ref).read() and "WAITING-FOR" in open(ref).read())
        pproj = os.path.join(tmp, "plan")
        run([PY, os.path.join(work, "tools", "new_project.py"), pproj, "--plugin-mode"])
        tmd = os.path.join(pproj, ".agents", "workarea", "tasks.md")
        post = lambda: run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=pproj, env=penv,
                           inp=json.dumps({"session_id": "p", "turn_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Write",
                                           "tool_use_id": "u" + str(len(os.listdir(pproj))), "cwd": pproj, "tool_input": {"file_path": tmd}}))
        run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=pproj, env=penv,
            inp=json.dumps({"session_id": "p", "turn_id": "t", "cwd": pproj}))
        open(tmd, "w").write("# plan\n- [ ] AAAA1111 first - main : OPEN 2026-09-06 10:00:00\n")
        r = post()
        check("well-formed tasks.md write passes silently", r.returncode == 0 and r.stdout.strip() == "" and r.stderr.strip() == "", r.stdout + r.stderr)
        open(tmd, "w").write("# plan\n- [ ] AAAA1111 first - main : DONE 2026-09-06\n")
        r = post()
        check("malformed tasks.md write is blocked with the grammar", r.returncode == 2 and "validation FAILED" in r.stderr
              and "<OPEN|IN-PROGRESS|WAITING-FOR|COMPLETED>" in r.stderr and "line 2" in r.stderr, r.stdout + r.stderr)
        open(tmd, "w").write("# plan\n- [ ] AAAA1111 first - main : OPEN 2026-09-06 10:00:00\n- [x] AAAA1111 dup - main : COMPLETED 2026-09-06 10:00:00 [ev:Tstevt01]\n")
        r = post()
        check("duplicate TaskID is blocked", r.returncode == 2 and "duplicate TaskID" in r.stderr, r.stderr[:200])
        open(tmd, "w").write("# plan\n- [x] AAAA1111 first - main : COMPLETED 2026-09-06 10:00:00\n")
        r = post()
        check("completed leaf without evidence is advisory only",
              r.returncode == 0 and "evidence-of-closing" in r.stdout and '"systemMessage"' in r.stdout, r.stdout + r.stderr)
        open(os.path.join(pproj, ".agents", "workarea", "tasks-archive.md"), "w").write("- garbage line\n")
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=pproj, env=penv,
                inp=json.dumps({"session_id": "p", "turn_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "uarch", "cwd": pproj, "tool_input": {}}))
        check("tasks-archive.md is never linted", r.returncode == 0 and r.stderr.strip() == "", r.stderr)
        lint = os.path.join(plug, "skills", "yaml-log-entry", "assets", "tasks_lint.py")
        r = run([PY, lint, tmd, "--json"])
        check("tasks_lint --json exit 1 on warnings only", r.returncode == 1 and json.loads(r.stdout)["errors"] == [] and json.loads(r.stdout)["warnings"], r.stdout)
        open(tmd, "w").write("# Block A\n- [x] AAAA1111 a - main : COMPLETED 2026-09-06 10:00:00 [ev:Tstevt01]\n# Block B\n- [ ] BBBB2222 b - main : OPEN 2026-09-06 10:00:00\n")
        r = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=pproj, env=penv)
        check("STATE.md reports archivable plan blocks", "Archivable plan blocks: 1" in r.stdout and "Block A" in r.stdout, r.stdout[-400:])

        # 14 — parallel sessions
        sproj = os.path.join(tmp, "sessions")
        run([PY, os.path.join(work, "tools", "new_project.py"), sproj, "--plugin-mode"])
        senv = penv | {"TKSFW_USER": "carlos"}
        wa = os.path.join(sproj, ".agents", "workarea")
        def hook(script, sid, turn, extra, env=senv, args=()):
            return run([PY, os.path.join(plug, "hooks", script), *args], cwd=sproj, env=env,
                       inp=json.dumps({"session_id": sid, "turn_id": turn, "cwd": sproj, **extra}))
        def post(sid, turn, path, tool="Write"):
            ti = {"file_path": os.path.join(sproj, path)} if tool == "Write" else {"command": "ls"}
            return hook("track_edits.py", sid, turn, {"hook_event_name": "PostToolUse", "tool_name": tool,
                                                      "tool_use_id": f"u{len(os.listdir(wa))}{turn}{abs(hash(path)) % 997}", "tool_input": ti})
        def token_of(sid):
            for f in os.listdir(os.path.join(wa, ".hook-state", "sessions")):
                d = json.load(open(os.path.join(wa, ".hook-state", "sessions", f)))
                if d["harness_session_id"] == sid:
                    return d["token"]
            return ""
        def change_entry(eid, owner, user):
            return (f"- {eid}:\n    AuthorAgent: main\n    Model: gpt-5.6-sol\n    Timestamp: \"2026-09-06 10:00:00\"\n"
                    f"    OwnerSessionId: {owner}\n    OwnerSessionUserName: {user}\n    Layer: PROJECT\n    Title: \"{eid}\"\n"
                    "    Description: |-\n      x\n    StateBefore: |-\n      x\n    StateAfter: |-\n      x\n    Remarks: |-\n      x\n")
        rA = hook("inject_state.py", "SA", "a1", {"source": "startup"})
        ctxA = json.loads(rA.stdout)["hookSpecificOutput"]["additionalContext"]
        tA = token_of("SA")
        check("SessionStart injects session token and operator", len(tA) == 8 and f"Session token: {tA}" in ctxA and "Operator: carlos" in ctxA, ctxA[:300])
        rB = hook("inject_state.py", "SB", "b1", {"source": "startup"})
        ctxB = json.loads(rB.stdout)["hookSpecificOutput"]["additionalContext"]
        tB = token_of("SB")
        check("second session gets its own token and a warning about the first", tB and tB != tA and "WARNING: 1 other session" in ctxB and tA in ctxB, ctxB[:400])
        r = hook("inject_state.py", "SA", "a1", {"source": "resume"})
        check("resume keeps the same token", f"Session token: {tA}" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
        ch = os.path.join(wa, "changes.yaml")
        open(ch, "w").write(change_entry("Aaaa1111", tA, "carlos"))
        r = post("SA", "a1", ".agents/workarea/changes.yaml")
        check("entry with owner fields accepted", r.returncode == 0, r.stderr[:300])
        open(ch, "a").write(change_entry("Bbbb2222", tB, "bob").replace(f"    OwnerSessionId: {tB}\n    OwnerSessionUserName: bob\n", ""))
        r = post("SB", "b1", ".agents/workarea/changes.yaml")
        check("new entry without owner fields is rejected", r.returncode == 2 and "OwnerSessionId" in r.stderr, r.stderr[:300])
        open(ch, "w").write(change_entry("Aaaa1111", tA, "carlos") + change_entry("Bbbb2222", tB, "bob"))
        r = post("SB", "b1", ".agents/workarea/changes.yaml")
        check("corrected entry accepted", r.returncode == 0, r.stderr[:300])
        open(ch, "w").write(change_entry("Aaaa1111", tA, "carlos"))          # byte-identical to A's last view
        r = post("SA", "a1", ".agents/workarea/changes.yaml")
        check("A-B-A rewrite that drops another session's entry is blocked as LOST UPDATE",
              r.returncode == 2 and "LOST UPDATE" in r.stderr and "Bbbb2222" in r.stderr and tB in r.stderr, r.stderr[:300])
        open(ch, "w").write(change_entry("Aaaa1111", tA, "carlos") + change_entry("Bbbb2222", tB, "bob"))
        r = post("SA", "a1", ".agents/workarea/changes.yaml")
        check("restored file accepted", r.returncode == 0, r.stderr[:300])
        # attribution: B's unnamed hook run sees A's ledger write as external
        open(ch, "a").write(change_entry("Cccc3333", tA, "carlos"))
        post("SA", "a1", ".agents/workarea/changes.yaml")
        open(os.path.join(sproj, "AGENTS.md"), "a").write("\n# touched by A\n")
        post("SA", "a1", "AGENTS.md")
        r = post("SB", "b1", "x", tool="Bash")
        jl = [json.loads(l) for l in open(os.path.join(wa, ".hook-state", "journal.jsonl"))]
        lastB = [e for e in jl if e.get("session") == tB][-1]["changed"]
        att = {c["path"].split("/")[-1]: c.get("attrib") for c in lastB}
        check("B sees A's ledger entry as external and A's unnamed edit as ambiguous",
              att.get("changes.yaml") == "external" and att.get("AGENTS.md") == "ambiguous", str(att))
        r = hook("check_ledgers_on_stop.py", "SB", "b1", {"hook_event_name": "Stop"})
        check("B's Stop reports the external change and still reminds about the ambiguous edit",
              "other session(s) observed" in r.stdout and "AGENTS.md" in r.stdout, r.stdout[:300])
        # decisions: own removal allowed, foreign blocked
        dec = os.path.join(wa, "decisions.yaml")
        good_dec = open(os.path.join(REPO, "template", ".agents", "skills", "yaml-log-entry", "tests", "fixtures", "good_decisions.yaml")).read()
        def dec_entry(eid, owner, user):
            return good_dec.replace("Tstdec01", eid).replace('    LastUpdate: "2026-07-21 10:00:00"\n', f'    LastUpdate: "2026-07-21 10:00:00"\n    OwnerSessionId: {owner}\n    OwnerSessionUserName: {user}\n')
        open(dec, "w").write(dec_entry("Dddd1111", tA, "carlos") + dec_entry("Eeee2222", tB, "bob"))
        r = post("SA", "a2", ".agents/workarea/decisions.yaml")
        check("decisions with owners accepted", r.returncode == 0, r.stderr[:300])
        open(dec, "w").write(dec_entry("Eeee2222", tB, "bob"))
        r = post("SA", "a2", ".agents/workarea/decisions.yaml")
        check("removing an OWN decision entry is allowed (mutable ledger)", r.returncode == 0, r.stderr[:300])
        open(dec, "w").write(dec_entry("Ffff3333", tA, "carlos"))
        r = post("SA", "a2", ".agents/workarea/decisions.yaml")
        check("removing ANOTHER session's decision entry is blocked", r.returncode == 2 and "Eeee2222" in r.stderr, r.stderr[:300])
        # tasks: removal vs archive
        tmd = os.path.join(wa, "tasks.md")
        open(tmd, "w").write("# plan\n- [ ] T001 a - main : OPEN 2026-09-06 10:00:00\n- [ ] T002 b - main : OPEN 2026-09-06 10:00:00\n")
        post("SA", "a3", ".agents/workarea/tasks.md")
        open(tmd, "w").write("# plan\n- [ ] T002 b - main : OPEN 2026-09-06 10:00:00\n")
        r = post("SA", "a3", ".agents/workarea/tasks.md")
        check("TaskID removed without archiving is blocked", r.returncode == 2 and "T001" in r.stderr, r.stderr[:300])
        open(os.path.join(wa, "tasks-archive.md"), "w").write("- [ ] T001 a - main : OPEN 2026-09-06 10:00:00\n")
        r = post("SA", "a3", ".agents/workarea/tasks.md")
        check("archive move is accepted", r.returncode == 0, r.stderr[:300])
        # per-session cap
        for i in range(4):
            hook("subagent_track.py", "SA", "a4", {"hook_event_name": "SubagentStart", "agent_id": f"sa{i}", "agent_type": "x-builder"}, args=["--start"])
        rA = hook("route_model.py", "SA", "a4", {"hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "sources-researcher"}})
        rB = hook("route_model.py", "SB", "b4", {"hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "sources-researcher"}})
        check("live-subagent cap is per session", '"deny"' in rA.stdout and '"allow"' in rB.stdout, rA.stdout[:200] + rB.stdout[:200])
        hook("check_ledgers_on_stop.py", "SA", "a4", {"hook_event_name": "Stop"})
        rA = hook("route_model.py", "SA", "a5", {"hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "sources-researcher"}})
        check("A's Stop clears only A's live set", '"allow"' in rA.stdout, rA.stdout[:200])
        # work areas keyed by session
        watool = os.path.join(plug, "skills", "delegate-work", "assets", "workarea.py")
        r1 = run([PY, watool, "create", "x-builder", "T002", "--session", tA], cwd=sproj, env=senv)
        r2 = run([PY, watool, "create", "x-builder", "T002", "--session", tA], cwd=sproj, env=senv)
        r3 = run([PY, watool, "create", "x-builder", "T002", "--session", tB], cwd=sproj, env=senv)
        check("work areas: <session>.<task>.<instance>, instances allocated, sessions separate",
              r1.stdout.strip().endswith(f"{tA}.T002.0") and r2.stdout.strip().endswith(f"{tA}.T002.1") and r3.stdout.strip().endswith(f"{tB}.T002.0"),
              r1.stdout + r2.stdout + r3.stdout + r3.stderr)
        r = run([PY, watool, "create", "x-builder", "T002"], cwd=sproj, env=senv)
        check("--session required while two sessions are active", r.returncode != 0 and "2 sessions" in r.stderr, r.stderr)
        stamp = run([PY, os.path.join(plug, "skills", "yaml-log-entry", "assets", "new_entry_id.py"), ch, "--stamp", "--session", tA], cwd=sproj, env=senv)
        check("new_entry_id --stamp prints owner fields", f"OwnerSessionId: {tA}" in stamp.stdout and "OwnerSessionUserName: carlos" in stamp.stdout, stamp.stdout)
        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md carries the ownership rule and the session-keyed work-area line",
              "OwnerSessionId" in agents_md and "<session-token>.<task-id>.<instance>" in agents_md)

        # 15 — operator configuration item
        cfgdir = os.path.join(tmp, "cfg")
        oenv = {k: v for k, v in penv.items() if k != "TKSFW_USER"} | {"TKSFW_CONFIG_DIR": cfgdir, "GIT_CONFIG_GLOBAL": os.path.join(tmp, "nogitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        np_ = os.path.join(work, "tools", "new_project.py")
        r = run([PY, np_, "--show-operator"], cwd=tmp, env=oenv)
        check("--show-operator exits 1 when nothing resolves", r.returncode == 1 and "UNKNOWN" in r.stderr, r.stdout + r.stderr)
        r = run([PY, np_, "--set-operator", "Carlos Veira"], cwd=tmp, env=oenv)
        cfg = os.path.join(cfgdir, "user.toml")
        check("--set-operator writes user.toml", r.returncode == 0 and os.path.isfile(cfg) and 'name = "Carlos Veira"' in open(cfg).read() and "schema = 1" in open(cfg).read(), r.stdout + r.stderr)
        r = run([PY, np_, "--show-operator"], cwd=tmp, env=oenv)
        check("file source resolved", r.returncode == 0 and "Carlos Veira" in r.stdout and "source: file" in r.stdout, r.stdout)
        r = run([PY, np_, "--show-operator"], cwd=tmp, env=oenv | {"TKSFW_USER": "ci-bot"})
        check("TKSFW_USER overrides the file", "ci-bot" in r.stdout and "source: env" in r.stdout, r.stdout)
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=sproj, env=oenv,
                inp=json.dumps({"session_id": "SC", "turn_id": "c1", "source": "startup", "cwd": sproj}))
        check("SessionStart shows the configured operator", "Operator: Carlos Veira" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"], r.stdout[:300])
        stamp = run([PY, os.path.join(plug, "skills", "yaml-log-entry", "assets", "new_entry_id.py"), ch, "--stamp", "--session", tA], cwd=sproj, env=oenv)
        check("new_entry_id --stamp reads the same config item", "OwnerSessionUserName: Carlos Veira" in stamp.stdout, stamp.stdout)

        # 16 — ks + archives
        ks = os.path.join(plug, "bin", "ks")
        check("ks bundled in the plugin with completion", os.path.isfile(ks) and os.access(ks, os.X_OK) and os.path.isfile(os.path.join(plug, "bin", "ks-completion.sh")))
        khome = os.path.join(tmp, "kshome")
        kenv = penv | {"TKSFW_CONFIG_DIR": os.path.join(tmp, "kscfg"), "HOME": khome, "TKSFW_USER": "carlos"}
        os.makedirs(khome, exist_ok=True)
        r = run([PY, ks, "self", "version"], env=kenv)
        check("ks self version (plugin home via script location)", r.returncode == 0 and "plugin at" in r.stdout and open(os.path.join(REPO, "VERSION")).read().strip() in r.stdout, r.stdout + r.stderr)
        r = run([PY, ks, "self", "install", "--bin-dir", os.path.join(tmp, "ksbin")], env=kenv)
        check("ks self install: symlink + home recorded", r.returncode == 0 and os.path.islink(os.path.join(tmp, "ksbin", "ks"))
              and 'home = "' in open(os.path.join(tmp, "kscfg", "user.toml")).read(), r.stdout + r.stderr)
        r = run([PY, ks, "operator", "set", "Carlos Veira"], env=kenv)
        r2 = run([PY, ks, "operator", "show"], env={k: v for k, v in kenv.items() if k != "TKSFW_USER"})
        check("ks operator set/show", r.returncode == 0 and "Carlos Veira" in r2.stdout and "source: file" in r2.stdout, r2.stdout + r2.stderr)
        kproj = os.path.join(tmp, "ksproj")
        os.makedirs(kproj)
        r = run([PY, ks, "project", "init"], cwd=kproj, env=kenv)
        check("ks project init (plugin mode by default)", r.returncode == 0 and os.path.isfile(os.path.join(kproj, ".agents", ".tksfw.json")) and not os.path.exists(os.path.join(kproj, ".agents", "hooks")), r.stdout + r.stderr)
        r = run([PY, ks, "project", "status"], cwd=kproj, env=kenv)
        check("ks project status", r.returncode == 0 and "ARMED" in r.stdout and "mode: plugin" in r.stdout and "drift" in r.stdout, r.stdout + r.stderr)
        r = run([PY, ks, "project", "drift"], cwd=kproj, env=kenv)
        check("ks project drift: fresh project has none", r.returncode == 0 and "no drift" in r.stdout, r.stdout + r.stderr)
        open(os.path.join(kproj, "AGENTS.md"), "a").write("\n# local\n")
        r = run([PY, ks, "project", "drift", "--json"], cwd=kproj, env=kenv)
        check("ks project drift --json reports the edited file", r.returncode == 1 and "AGENTS.md" in json.loads(r.stdout)["edited"], r.stdout[:200] + r.stderr)
        r = run([PY, ks, "project", "disable"], cwd=kproj, env=kenv)
        r2 = run([PY, ks, "project", "enable"], cwd=kproj, env=kenv)
        check("ks project disable/enable", "DISARMED" in r.stdout and "ARMED" in r2.stdout, r.stdout + r2.stdout)
        r = run([PY, ks, "routing", "use", "ibm"], cwd=kproj, env=kenv)
        mt = open(os.path.join(kproj, ".agents", "models.toml")).read()
        r2 = run([PY, ks, "routing", "show"], cwd=kproj, env=kenv | {"CODEX_HOME": os.path.join(tmp, "nocodex")})
        check("ks routing use pins `selected` and the hook honours it", r.returncode == 0 and 'selected = "ibm"' in mt and "selected_by=selected" in r2.stdout, r.stdout + r2.stdout + r2.stderr)
        r = run([PY, ks, "routing", "use", "nope"], cwd=kproj, env=kenv)
        check("ks routing use refuses an unknown table", r.returncode != 0 and "no [routing.nope]" in r.stderr, r.stderr)
        r = run([PY, ks, "routing", "use", "--clear"], cwd=kproj, env=kenv)
        check("ks routing use --clear", r.returncode == 0 and not re.search(r"^selected\s*=", open(os.path.join(kproj, ".agents", "models.toml")).read(), re.M), r.stdout)
        r = run([PY, ks, "routing", "check"], cwd=kproj, env=kenv)
        r2 = run([PY, ks, "routing", "resolve", "sources-researcher"], cwd=kproj, env=kenv)
        check("ks routing check/resolve", r.returncode == 0 and '"model": "gpt-5.6-luna"' in r2.stdout, r.stdout + r2.stdout)
        # archives
        kwa = os.path.join(kproj, ".agents", "workarea")
        def ev(eid, task, ts, status):
            return (f"- {eid}:\n    TaskID: {task}\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"{ts}\"\n    OwnerSessionId: Xk9Qm2Ab\n"
                    f"    OwnerSessionUserName: carlos\n    EventType: TASK\n    Title: \"ev {eid}\"\n    Remarks: |-\n      x\n    Status: {status}\n")
        open(os.path.join(kwa, "events.yaml"), "w").write(ev("Evnt0001", "T001", "2026-01-05 10:00:00", "COMPLETED") + ev("Evnt0002", "T002", "2026-01-06 10:00:00", "OPEN") + ev("Evnt0003", "T002", "2026-09-01 10:00:00", "COMPLETED"))
        open(os.path.join(kwa, "tasks.md"), "w").write("# Block A\n- [x] T001 a - main : COMPLETED 2026-01-05 10:00:00 [ev:Evnt0001]\n# Block B\n- [ ] T002 b - main : OPEN 2026-01-06 10:00:00\n")
        open(os.path.join(kwa, "tasks-archive.md"), "w").write("# Old\n- [x] T000 z - main : COMPLETED 2025-12-01 10:00:00 [ev:Evnt0000]\n")
        r = run([PY, ks, "ledger", "archive-plan", "--dry-run"], cwd=kproj, env=kenv)
        check("ks ledger archive-plan --dry-run changes nothing", r.returncode == 0 and "Block A" in r.stdout and not os.path.exists(os.path.join(kwa, "archive", "tasks.md")), r.stdout)
        r = run([PY, ks, "ledger", "archive-plan"], cwd=kproj, env=kenv)
        at = open(os.path.join(kwa, "archive", "tasks.md")).read()
        check("archive-plan migrates tasks-archive.md and moves the superseded block",
              r.returncode == 0 and "T000" in at and "T001" in at and not os.path.exists(os.path.join(kwa, "tasks-archive.md"))
              and "T001" not in open(os.path.join(kwa, "tasks.md")).read() and "T002" in open(os.path.join(kwa, "tasks.md")).read(), r.stdout + r.stderr)
        r = run([PY, ks, "ledger", "archive", "events", "--before", "2026-06-01"], cwd=kproj, env=kenv)
        live = open(os.path.join(kwa, "events.yaml")).read(); arch = open(os.path.join(kwa, "archive", "events.yaml")).read()
        check("ks ledger archive moves only closed, old events", r.returncode == 0 and "Evnt0001" in arch and "Evnt0001" not in live
              and "Evnt0002" in live and "Evnt0003" in live and "OwnerSessionId: Xk9Qm2Ab" in arch, r.stdout + r.stderr)
        r = run([PY, ks, "ledger", "check"], cwd=kproj, env=kenv)
        check("ks ledger check passes with the archived evidence link", r.returncode == 0 and "PASS" in r.stdout, r.stdout[-300:] + r.stderr)
        r = run([PY, ks, "ledger", "find", "T001", "--refs"], cwd=kproj, env=kenv)
        check("ks ledger find locates the archived task and its referencing event",
              r.returncode == 0 and "archive/tasks.md" in r.stdout and "Evnt0001" in r.stdout and "archive/events.yaml" in r.stdout, r.stdout)
        r = run([PY, ks, "ledger", "find", "Nope0000"], cwd=kproj, env=kenv)
        check("ks ledger find: not found → exit 1", r.returncode == 1)
        # hook guard vs archives
        kpost = lambda path, turn="k1": run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=kproj, env=kenv,
                                             inp=json.dumps({"session_id": "SK", "turn_id": turn, "hook_event_name": "PostToolUse", "tool_name": "Write",
                                                             "tool_use_id": f"u{abs(hash(path + open(os.path.join(kproj, path)).read())) % 99991}", "cwd": kproj,
                                                             "tool_input": {"file_path": os.path.join(kproj, path)}}))
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=kproj, env=kenv, inp=json.dumps({"session_id": "SK", "turn_id": "k1", "source": "startup", "cwd": kproj}))
        # move Evnt0003 by hand the right way: archive first, then remove
        open(os.path.join(kwa, "archive", "events.yaml"), "a").write(ev("Evnt0003", "T002", "2026-09-01 10:00:00", "COMPLETED"))
        r1 = kpost(".agents/workarea/archive/events.yaml")
        open(os.path.join(kwa, "events.yaml"), "w").write(ev("Evnt0002", "T002", "2026-01-06 10:00:00", "OPEN"))
        r2 = kpost(".agents/workarea/events.yaml")
        check("guard: archive-first move of a ledger entry is accepted", r1.returncode == 0 and r2.returncode == 0, r1.stderr[:200] + r2.stderr[:200])
        open(os.path.join(kwa, "events.yaml"), "w").write("[]\n")
        r = kpost(".agents/workarea/events.yaml")
        check("guard: removing an unarchived entry is still blocked", r.returncode == 2 and "Evnt0002" in r.stderr and "archive/events.yaml" in r.stderr, r.stderr[:300])
        open(os.path.join(kwa, "events.yaml"), "w").write(ev("Evnt0002", "T002", "2026-01-06 10:00:00", "OPEN"))
        kpost(".agents/workarea/events.yaml")
        open(os.path.join(kwa, "archive", "events.yaml"), "w").write(ev("Evnt0001", "T001", "2026-01-05 10:00:00", "COMPLETED"))
        r = kpost(".agents/workarea/archive/events.yaml")
        check("guard: archives never lose an ID", r.returncode == 2 and "archive lost" in r.stderr and "Evnt0003" in r.stderr, r.stderr[:300])
        r = run([PY, ks, "harness", "retrust"], cwd=kproj, env=kenv)
        r2 = run([PY, ks, "harness", "retrust", "--ack"], cwd=kproj, env=kenv)
        r3 = run([PY, ks, "harness", "retrust"], cwd=kproj, env=kenv)
        check("ks harness retrust: unknown → ack → clean", r.returncode == 1 and r2.returncode == 0 and r3.returncode == 0 and "no change" in r3.stdout, r.stdout + r3.stdout)
        r = run([PY, ks, "doctor"], cwd=kproj, env=kenv)
        check("ks doctor runs end to end", r.returncode == 0 and "== project" in r.stdout and "FAIL ·" in r.stdout, r.stdout[-300:] + r.stderr)
        r = run([PY, ks, "dev", "test"], cwd=kproj, env=kenv)
        check("ks dev refuses to run from a plugin home", r.returncode != 0 and "checkout" in r.stderr, r.stderr)
        r = run([PY, os.path.join(REPO, "tools", "ks"), "self", "version"], env=kenv | {"TKSFW_HOME": REPO})
        check("ks from the checkout reports repo home", "repo at" in r.stdout, r.stdout)

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
