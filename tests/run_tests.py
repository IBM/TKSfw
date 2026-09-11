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
  7. Model routing: config.toml validates; route_model.py resolves Codex/Claude spawns (table
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
 17. Live reconfiguration (1.6.0): UserPromptSubmit notice for routing/operator/armed changes and
     external file changes; ks effect lines; `routing use` refuses while subagents run; `ks self setup`
     idempotent stanzas; docs present
 18. Partitioned ledgers (1.7.0, exercised inside 14/16): own-shard writes accepted, foreign shard and
     legacy writes rejected, own append-only drop = lost update, decisions append-only with DECISION
     events, STATE.md sessions section, prompt notice with titles, sync conflict copies reported,
     archive refuses while sessions are active, per-host hook state
 19. Excel export (1.8.0): xlsx_lite produces a valid workbook (zip + XML parsed; openpyxl when
     available), ks ledger export all / by kind / --csv / --archive / --session
 20. ks project reset (1.9.0): dry run, refusals (active session, no --yes, unmerged worktree),
     --archive moves ledgers/plan/archives/agents to .agents/history/<stamp>, clear deletes, hook
     state always deleted, registry kept unless --registry, --keep-agents, manifest `resets`,
     generation line at SessionStart and in STATE.md, history never watched
 21. Ledger digest (2.0.0): blocked gates / in force / pending / issues / in flight / lessons / changes
     in STATE.md within budget; task view with evidence chain; SubagentStart briefing with the open
     handoff, global in-force decisions and lessons; prompt notice for new issues and failed gates;
     ks ledger digest; AGENTS.md consult rule; [state] limits honoured
 22. Human in the Loop (2.1.0, default OR since 2.3.0): default threshold HIGH or HARD; hook rejects a new above-threshold
     AUTO-MODE decision and a Worker-accepted one; compliant OPEN/OPERATOR passes; legacy entries warn
     only; advisory mode warns; ks hil show/set (validation, effect line, live prompt notice); digest
     marks pending HIL decisions; doctor line; AGENTS.md section
 23. Project layers L3/L4 (2.2.0): layers.py resolves by convention (KS_PROJECT.md / KS_SPEC.md),
     by the manifest `layers` stanza and by arguments; declared-but-missing → exit 4, nothing → exit 3,
     L4 alone is valid; frontmatter title/ks_layer mismatch warning; SessionStart emits the
     `<!-- tksfw:layers -->` block even on a fresh project, statuses new → unchanged → changed after an
     edit, the block is re-journaled; `state` section still marked; layer edits are classified
     `layer:l3/l4`, watched, reported by the Stop hook and STATE.md; `ks layers resolve|pin|journal|
     section`, `ks project status` line; `new_project --update` keeps the `layers` stanza; ks-start
     skill bundled and mirrored; Codex prompts reference the new files; AGENTS.md section + no legacy
     `_project-archetype.md` mention; kernel < 19,000 B
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import time
import shutil
import glob
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


HOST = "testhost"


def host_state(project):
    """This host's hook-state dir (1.7.0: .hook-state/hosts/<host>/)."""
    return os.path.join(project, ".agents", "workarea", ".hook-state", "hosts", HOST)



AGENT_NAMES = ("sources-researcher", "report-builder", "x-planner", "output-validator", "x-builder", "data-fetcher", "cv-writer", "final-writer", "pricing-reviewer", "manual")


def seed_agents(root, names=AGENT_NAMES):
    """Agent definitions the spawn tests refer to (3.4.1: the hook denies spawns of undefined agents)."""
    d = os.path.join(root, ".agents", "agents")
    os.makedirs(d, exist_ok=True)
    for n in names:
        p = os.path.join(d, n + ".toml")
        if not os.path.exists(p):
            open(p, "w").write(f'name = "{n}"\ndescription = "MUST BE USED for {n} work."\ndeveloper_instructions = "Do the {n} work."\n')


def run(cmd, cwd=None, env=None, inp=None):
    e = os.environ.copy()
    e.pop("CLAUDE_PROJECT_DIR", None)
    e.pop("TKSFW_PROJECT_ROOT", None)
    if env:
        e.update(env)
    # No inherited stdin: when the suite runs from a terminal, an interactive prompt in a child
    # (e.g. `ks project reset` confirmation) would otherwise wait for the keyboard until the timeout.
    return subprocess.run(cmd, cwd=cwd, env=e, input=inp, capture_output=True, text=True, timeout=120,
                          **({} if inp is not None else {"stdin": subprocess.DEVNULL}))


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
        check("skills bundled", skills == ["define-agent", "delegate-work", "ks-reload", "ks-start", "register-deliverables", "tksfw-init", "verify-integrity", "verify-sources", "yaml-log-entry"], str(skills))
        check("skill tests dropped from bundle", not os.path.exists(os.path.join(plug, "skills", "yaml-log-entry", "tests")))
        check("validator present in bundle", os.path.isfile(os.path.join(plug, "skills", "yaml-log-entry", "assets", "validate_yaml_log.py")))

        # 3 — plugin mode: scratch project with only the method instance
        proj = os.path.join(tmp, "proj")
        r = run([PY, os.path.join(work, "tools", "new_project.py"), proj, "--plugin-mode"])
        check("new_project.py --plugin-mode", r.returncode == 0, r.stdout + r.stderr)
        seed_agents(proj)
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
        seed_agents(full, ("x-planner", "output-validator", "x-builder", "report-builder", "sources-researcher"))
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
        base_env = {"CODEX_HOME": codex_home, "ANTHROPIC_BASE_URL": "", "TKSFW_ROUTING": "", "TKSFW_HOST": HOST}
        base_env = {k: v for k, v in base_env.items() if v} | {"CODEX_HOME": codex_home}
        rm = os.path.join(full, ".agents", "hooks", "route_model.py")
        r = run([PY, rm, "--check"], cwd=full, env=base_env)
        check("routing: config.toml --check", r.returncode == 0 and "ok" in r.stdout, r.stdout + r.stderr)
        r = run([PY, rm, "--print", "--codex"], cwd=full, env=base_env)
        check("routing: --print selects [routing.ibm-anthropic] from CODEX_HOME (first table matching provider ibm)", r.returncode == 0 and "routing='ibm-anthropic'" in r.stdout and "(match)" in r.stdout, r.stdout)
        r = run([PY, rm, "--print", "--claude"], cwd=full, env={k: v for k, v in base_env.items() if k != "CODEX_HOME"} | {"CODEX_HOME": os.path.join(tmp, "nocodex")})
        check("routing: Claude Code without a base-URL match falls to default_routing = ibm-anthropic-cc", "routing='ibm-anthropic-cc'" in r.stdout and "selected_by=default_routing" in r.stdout, r.stdout)
        r, out = hook("spawn_agent", {"task_name": "sources-researcher_scan", "message": "m", "fork_turns": "none"},
                      env=base_env, extra={"turn_id": "t1"})
        hs = out.get("hookSpecificOutput", {})
        check("routing codex: researcher → haiku/low via updatedInput (ibm-anthropic wins the provider match)",
              hs.get("permissionDecision") == "allow" and hs.get("updatedInput", {}).get("model") == "claude-haiku-4-5"
              and hs["updatedInput"].get("reasoning_effort") == "low" and hs["updatedInput"].get("task_name") == "sources-researcher_scan"
              and "claude-haiku-4-5" in hs.get("additionalContext", ""), r.stdout + r.stderr)
        r, out = hook("Agent", {"subagent_type": "report-builder", "prompt": "p", "description": "d"},
                      env=base_env | {"ANTHROPIC_BASE_URL": "https://openrouter.ai/api/v1"}, extra={"prompt_id": "p1"})
        hs = out.get("hookSpecificOutput", {})
        check("routing claude: builder → openrouter table by ANTHROPIC_BASE_URL; spawn carries the alias, context the id (3.3.0)",
              hs.get("permissionDecision") == "allow" and hs.get("updatedInput", {}).get("model") == "sonnet"
              and "anthropic/claude-sonnet-latest" in hs.get("additionalContext", "") and "ANTHROPIC_DEFAULT_SONNET_MODEL" in hs.get("additionalContext", "")
              and "reasoning_effort" not in hs.get("updatedInput", {}), r.stdout + r.stderr)
        r, out = hook("Agent", {"subagent_type": "x-planner", "prompt": "p"}, env=base_env, extra={"prompt_id": "p2"})
        hs = out.get("hookSpecificOutput", {})
        check("routing: TKSFW_ROUTING override", hook("Agent", {"subagent_type": "x-planner", "prompt": "p"},
              env=base_env | {"TKSFW_ROUTING": "openrouter"}, extra={"prompt_id": "p3"})[1]
              .get("hookSpecificOutput", {}).get("updatedInput", {}).get("model") == "opus")
        check("routing claude without base URL: default_routing → ibm-anthropic-cc (1M sonnet/opus)",
              hs.get("permissionDecision") == "allow" and hs.get("updatedInput", {}).get("model") == "opus" and "claude-opus-5[1m]" in hs.get("additionalContext", "") and "[routing.ibm-anthropic-cc]" in hs.get("additionalContext", ""), r.stdout)
        r, out = hook("spawn_agent", {"agent_type": "atlas"}, env=base_env, extra={"turn_id": "t2"})
        hs = out.get("hookSpecificOutput", {})
        check("routing: unknown role denied", hs.get("permissionDecision") == "deny" and "atlas" in hs.get("permissionDecisionReason", ""), r.stdout)
        r, out = hook("Bash", {"command": "ls"}, env=base_env, extra={"turn_id": "t3"})
        check("routing: non-spawn tool untouched", r.returncode == 0 and out == {}, r.stdout + r.stderr)
        jl = os.path.join(host_state(full), "routing.jsonl")
        check("routing: decisions journaled", os.path.isfile(jl) and sum(1 for _ in open(jl)) >= 4)
        # plugin bundle: hook runs from the plugin dir against the plugin-mode project (has config.toml)
        check("plugin-mode project carries config.toml", os.path.isfile(os.path.join(proj, ".agents", "config.toml")))
        r, out = hook("spawn_agent", {"agent_type": "output-validator"}, env=base_env | {"CLAUDE_PLUGIN_ROOT": plug},
                      cwd=proj, script=os.path.join(plug, "hooks", "route_model.py"), extra={"turn_id": "t4"})
        hs = out.get("hookSpecificOutput", {})
        check("routing from plugin bundle: validator → opus/high",
              hs.get("updatedInput", {}).get("model") == "claude-opus-5" and hs["updatedInput"].get("reasoning_effort") == "high", r.stdout + r.stderr)
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
              r.returncode == 0 and 'model = "claude-haiku-4-5"' in t1 and 'model_reasoning_effort = "low"' in t1
              and 'model = "claude-opus-5"' in t2 and "Find sources." in t1 and t1.startswith("# tksfw:mirror")
              and 'model = "stale"' in src1, r.stdout + r.stderr + t1 + t2)
        md = os.path.join(full, ".claude", "agents", "sources-researcher.md")
        m = open(md).read() if os.path.isfile(md) else ""
        check("sync --models writes Claude mirror with model/effort/tools",
              "model: claude-haiku-4-5" in m and "effort: low" in m and "tools: Read" in m and "tksfw:mirror" in m and "Find sources." in m, m)
        r = run([PY, sync, "--models", "--check"], cwd=full, env=base_env)
        check("sync --models idempotent", r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stdout)
        with open(os.path.join(full, ".claude", "agents", "manual.md"), "w") as fh:
            fh.write("---\nname: manual\ndescription: x\n---\nhand made\n")
        r = run([PY, sync, "--models", "--routing", "openrouter"], cwd=full, env=base_env)
        t1 = open(os.path.join(codex_mirrors, "sources-researcher.toml")).read()
        check("sync --models --routing switches table", 'model = "google/gemini-flash-latest"' in t1 and os.path.isfile(os.path.join(full, ".claude", "agents", "manual.md")), r.stdout + t1)
        mt = os.path.join(full, ".agents", "config.toml")
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
              and 'model = ' not in open(cm).read()          # config.toml is in strip mode at this point
              and "model: claude-opus-5" in open(am).read() and "tools: Read" in open(am).read(),
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
              r.returncode == 0 and os.path.isfile(pcm) and 'model = "claude-haiku-4-5"' in open(pcm).read()   # fetcher → research tier
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
        check("re-enabled project: routing active again", r.returncode == 0 and '"model": "claude-opus-5"' in r2.stdout, r.stdout + r2.stdout)
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
              and os.path.isfile(os.path.join(init, "assets", "template", ".agents", "config.toml"))
              and open(os.path.join(init, "assets", "VERSION")).read().strip() == open(os.path.join(REPO, "VERSION")).read().strip()
              and not os.path.exists(os.path.join(init, "assets", "template", ".agents", "skills", "yaml-log-entry", "tests")))
        check("bootstrap stanzas bundled",
              all(os.path.isfile(os.path.join(plug, "bootstrap", f)) for f in ("AGENTS.global.md", "CLAUDE.global.md"))
              and ".agents/.tksfw.json" in open(os.path.join(plug, "bootstrap", "AGENTS.global.md")).read())
        np2 = os.path.join(tmp, "from-plugin")
        r = run([PY, os.path.join(init, "assets", "new_project.py"), np2, "--plugin-mode"])
        seed_agents(np2)
        mf = os.path.join(np2, ".agents", ".tksfw.json")
        check("project created from the plugin bundle (plugin mode, armed)",
              r.returncode == 0 and os.path.isfile(os.path.join(np2, "AGENTS.md")) and os.path.isfile(mf)
              and json.load(open(mf))["enabled"] is True and json.load(open(mf))["version"] == open(os.path.join(REPO, "VERSION")).read().strip()
              and not os.path.exists(os.path.join(np2, ".agents", "hooks")), r.stdout + r.stderr)
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=np2, env=penv,
                inp=json.dumps({"session_id": "n", "turn_id": "t", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "sources-researcher"}, "cwd": np2}))
        check("plugin hooks serve the bundle-created project", '"model": "claude-haiku-4-5"' in r.stdout, r.stdout + r.stderr)
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
        seed_agents(dproj)
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
        live = json.load(open(os.path.join(host_state(dproj), "subagents.json")))["live"]
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
        live = json.load(open(os.path.join(host_state(dproj), "subagents.json")))["live"]
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
        seed_agents(sproj)
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
        chA = os.path.join(wa, f"changes.{tA}.yaml")
        chB = os.path.join(wa, f"changes.{tB}.yaml")
        open(chA, "w").write(change_entry("Aaaa1111", tA, "carlos"))
        r = post("SA", "a1", f".agents/workarea/changes.{tA}.yaml")
        check("entry with owner fields in the own shard accepted", r.returncode == 0, r.stderr[:300])
        open(chB, "w").write(change_entry("Bbbb2222", tB, "bob").replace(f"    OwnerSessionId: {tB}\n    OwnerSessionUserName: bob\n", ""))
        r = post("SB", "b1", f".agents/workarea/changes.{tB}.yaml")
        check("new entry without owner fields is rejected", r.returncode == 2 and "OwnerSessionId" in r.stderr, r.stderr[:300])
        open(chB, "w").write(change_entry("Bbbb2222", tB, "bob"))
        r = post("SB", "b1", f".agents/workarea/changes.{tB}.yaml")
        check("corrected entry accepted", r.returncode == 0, r.stderr[:300])
        open(chB, "a").write(change_entry("Xxxx9999", tA, "carlos"))          # A writes into B's shard
        r = post("SA", "a1", f".agents/workarea/changes.{tB}.yaml")
        check("write to another session's shard is rejected as READ-ONLY", r.returncode == 2 and "READ-ONLY LEDGER" in r.stderr and tB in r.stderr, r.stderr[:300])
        open(chB, "w").write(change_entry("Bbbb2222", tB, "bob"))               # restore
        post("SA", "a1", f".agents/workarea/changes.{tB}.yaml")
        legacy = os.path.join(wa, "changes.yaml")
        open(legacy, "w").write(change_entry("Llll0000", tA, "carlos"))
        r = post("SA", "a1", ".agents/workarea/changes.yaml")
        check("write to the legacy unsuffixed ledger is rejected", r.returncode == 2 and "legacy" in r.stderr, r.stderr[:300])
        os.remove(legacy)
        post("SA", "a1", ".agents/workarea/changes.yaml")
        open(chA, "a").write(change_entry("Cccc3333", tA, "carlos"))
        post("SA", "a1", f".agents/workarea/changes.{tA}.yaml")
        open(chA, "w").write(change_entry("Aaaa1111", tA, "carlos"))          # own shard, entry dropped
        r = post("SA", "a1", f".agents/workarea/changes.{tA}.yaml")
        check("dropping an entry from the own append-only shard is a LOST UPDATE", r.returncode == 2 and "LOST UPDATE" in r.stderr and "Cccc3333" in r.stderr, r.stderr[:300])
        open(chA, "w").write(change_entry("Aaaa1111", tA, "carlos") + change_entry("Cccc3333", tA, "carlos"))
        r = post("SA", "a1", f".agents/workarea/changes.{tA}.yaml")
        check("restored shard accepted", r.returncode == 0, r.stderr[:300])
        # attribution: B's unnamed hook run sees A's shard write as external
        open(chA, "a").write(change_entry("Dddd4444", tA, "carlos"))
        post("SA", "a1", f".agents/workarea/changes.{tA}.yaml")
        open(os.path.join(sproj, "AGENTS.md"), "a").write("\n# touched by A\n")
        post("SA", "a1", "AGENTS.md")
        r = post("SB", "b1", "x", tool="Bash")
        jl = [json.loads(l) for l in open(os.path.join(host_state(sproj), "journal.jsonl"))]
        lastB = [e for e in jl if e.get("session") == tB][-1]["changed"]
        att = {c["path"].split("/")[-1]: c.get("attrib") for c in lastB}
        check("B sees A's shard as external and A's unnamed edit as ambiguous",
              att.get(f"changes.{tA}.yaml") == "external" and att.get("AGENTS.md") == "ambiguous", str(att))
        r = hook("check_ledgers_on_stop.py", "SB", "b1", {"hook_event_name": "Stop"})
        check("B's Stop reports the external change and still reminds about the ambiguous edit",
              "other session(s) observed" in r.stdout and "AGENTS.md" in r.stdout, r.stdout[:300])
        r = hook("track_edits.py", "SB", "b2", {"prompt": "hi"}, args=["--phase", "prompt"])
        # decisions: append-only shards; status via DECISION events
        decA = os.path.join(wa, f"decisions.{tA}.yaml")
        good_dec = open(os.path.join(REPO, "template", ".agents", "skills", "yaml-log-entry", "tests", "fixtures", "good_decisions.yaml")).read()
        def dec_entry(eid, owner, user):
            return good_dec.replace("Tstdec01", eid).replace('    LastUpdate: "2026-07-21 10:00:00"\n', f'    LastUpdate: "2026-07-21 10:00:00"\n    OwnerSessionId: {owner}\n    OwnerSessionUserName: {user}\n').replace("Status: ACCEPTED", "Status: OPEN")
        open(decA, "w").write(dec_entry("Dddd1111", tA, "carlos"))
        r = post("SA", "a2", f".agents/workarea/decisions.{tA}.yaml")
        check("decision in own shard accepted", r.returncode == 0, r.stderr[:300])
        open(decA, "w").write("[]\n")
        r = post("SA", "a2", f".agents/workarea/decisions.{tA}.yaml")
        check("removing an own decision entry is blocked (append-only since 1.7.0)", r.returncode == 2 and "Dddd1111" in r.stderr, r.stderr[:300])
        open(decA, "w").write(dec_entry("Dddd1111", tA, "carlos"))
        post("SA", "a2", f".agents/workarea/decisions.{tA}.yaml")
        evB = os.path.join(wa, f"events.{tB}.yaml")
        open(evB, "w").write(f"- Evdc0001:\n    TaskID: N/A\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"2026-09-07 12:00:00\"\n    OwnerSessionId: {tB}\n    OwnerSessionUserName: bob\n    EventType: DECISION\n    DecisionID: Dddd1111\n    Title: \"accept Dddd1111\"\n    Remarks: |-\n      x\n    Status: ACCEPTED\n")
        r = post("SB", "b2", f".agents/workarea/events.{tB}.yaml")
        rs = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=sproj, env=senv)
        check("B accepts A's decision through a DECISION event; STATE.md shows no open decision and lists both sessions",
              r.returncode == 0 and "Open decisions: 0" in rs.stdout and "## Sessions (ledger shards)" in rs.stdout and tA in rs.stdout and tB in rs.stdout, r.stderr[:200] + rs.stdout[-600:])
        r = hook("track_edits.py", "SA", "a3", {"prompt": "hi"}, args=["--phase", "prompt"])
        check("A's prompt notice summarises B's new entries with titles", f"Session {tB}" in r.stdout and "accept Dddd1111" in r.stdout, r.stdout[:400])
        open(os.path.join(wa, "changes (1).yaml"), "w").write(change_entry("Zzzz0000", tB, "bob"))
        rs = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=sproj, env=senv)
        check("sync conflict copy is reported in STATE.md", "SYNC CONFLICT COPIES" in rs.stdout and "changes (1).yaml" in rs.stdout, rs.stdout[-400:])
        os.remove(os.path.join(wa, "changes (1).yaml"))
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
        stamp = run([PY, os.path.join(plug, "skills", "yaml-log-entry", "assets", "new_entry_id.py"), chA, "--stamp", "--session", tA], cwd=sproj, env=senv)
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
        stamp = run([PY, os.path.join(plug, "skills", "yaml-log-entry", "assets", "new_entry_id.py"), chA, "--stamp", "--session", tA], cwd=sproj, env=oenv)
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
        ut = open(os.path.join(tmp, "kscfg", "user.toml")).read()
        check("ks operator set keeps the recorded home in user.toml (2.3.1)", 'home = "' in ut and 'name = "Carlos Veira"' in ut, ut)
        r = run([PY, ks, "self", "setup", "--operator", "Carlos Veira"], env=kenv, inp="")
        check("ks self setup keeps the recorded home too", 'home = "' in open(os.path.join(tmp, "kscfg", "user.toml")).read(), r.stdout + r.stderr)
        # ZIP path: the marketplace bundle is a valid home and `ks self install` works from plugins/tksfw/bin/ks
        import zipfile
        zdir = os.path.join(tmp, "ziphome")
        zfile = next((os.path.join(REPO, "dist", f) for f in os.listdir(os.path.join(REPO, "dist")) if re.fullmatch(r"tksfw-\d+\.\d+\.\d+\.zip", f)), None)
        if zfile:
            zipfile.ZipFile(zfile).extractall(zdir)
            zks = os.path.join(zdir, "tksfw", "plugins", "tksfw", "bin", "ks")
            zenv = dict(kenv); zenv["TKSFW_CONFIG_DIR"] = os.path.join(tmp, "zipcfg"); zenv.pop("TKSFW_HOME", None)
            r = run([PY, zks, "self", "install", "--bin-dir", os.path.join(tmp, "zipbin")], env=zenv)
            r2 = run([PY, zks, "self", "home"], env=zenv)
            check("ZIP bundle: `plugins/tksfw/bin/ks self install` works and records the plugin as home (getting-started step 2, path A)",
                  r.returncode == 0 and os.path.islink(os.path.join(tmp, "zipbin", "ks")) and r2.stdout.strip().endswith(os.path.join("tksfw", "plugins", "tksfw")), r.stdout + r.stderr + r2.stdout)
            gs = open(os.path.join(REPO, "docs", "getting-started.md"), encoding="utf-8").read()
            check("getting-started names the ZIP path to ks and the marketplace folder", "plugins/tksfw/bin/ks self install" in gs and "tksfw-marketplace" not in gs and "unzip tksfw-<v>.zip" in gs and "tools/ks self install" in gs)
            zenv2 = dict(zenv); zenv2["TKSFW_HOME"] = os.path.join(zdir, "tksfw")
            r = run([PY, zks, "self", "home"], env=zenv2)
            check("TKSFW_HOME may name the bundle folder; ks resolves the plugin inside it", r.stdout.strip().endswith(os.path.join("tksfw", "plugins", "tksfw")), r.stdout + r.stderr)
            check("bundle carries the docs and README", os.path.isfile(os.path.join(zdir, "tksfw", "docs", "getting-started.md")) and os.path.isfile(os.path.join(zdir, "tksfw", "README.md")))
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
        r = run([PY, ks, "routing", "use", "ibm-openai"], cwd=kproj, env=kenv)
        mt = open(os.path.join(kproj, ".agents", "config.toml")).read()
        r2 = run([PY, ks, "routing", "show"], cwd=kproj, env=kenv | {"CODEX_HOME": os.path.join(tmp, "nocodex")})
        check("ks routing use pins `selected` and the hook honours it", r.returncode == 0 and 'selected = "ibm-openai"' in mt and "selected_by=selected" in r2.stdout, r.stdout + r2.stdout + r2.stderr)
        r = run([PY, ks, "routing", "use", "nope"], cwd=kproj, env=kenv)
        check("ks routing use refuses an unknown table", r.returncode != 0 and "no [routing.nope]" in r.stderr, r.stderr)
        r = run([PY, ks, "routing", "use", "--clear"], cwd=kproj, env=kenv)
        check("ks routing use --clear", r.returncode == 0 and not re.search(r"^selected\s*=", open(os.path.join(kproj, ".agents", "config.toml")).read(), re.M), r.stdout)
        r = run([PY, ks, "routing", "check"], cwd=kproj, env=kenv)
        r2 = run([PY, ks, "routing", "resolve", "sources-researcher"], cwd=kproj, env=kenv)
        check("ks routing check/resolve", r.returncode == 0 and '"model": "claude-haiku-4-5"' in r2.stdout, r.stdout + r2.stdout)
        # archives
        kwa = os.path.join(kproj, ".agents", "workarea")
        def ev(eid, task, ts, status):
            return (f"- {eid}:\n    TaskID: {task}\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"{ts}\"\n    OwnerSessionId: Xk9Qm2Ab\n"
                    f"    OwnerSessionUserName: carlos\n    EventType: TASK\n    Title: \"ev {eid}\"\n    Remarks: |-\n      x\n    Status: {status}\n")
        open(os.path.join(kwa, "events.yaml"), "w").write(ev("Evnt0001", "T001", "2026-01-05 10:00:00", "COMPLETED") + ev("Evnt0002", "T002", "2026-01-06 10:00:00", "OPEN") + ev("Evnt0003", "T002", "2026-09-01 10:00:00", "COMPLETED"))   # legacy (pre-1.7.0) file
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
        # hook guard vs archives (own shard)
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=kproj, env=kenv, inp=json.dumps({"session_id": "SK", "turn_id": "k1", "source": "startup", "cwd": kproj}))
        tK = next(json.load(open(os.path.join(kwa, ".hook-state", "sessions", f)))["token"] for f in os.listdir(os.path.join(kwa, ".hook-state", "sessions"))
                  if json.load(open(os.path.join(kwa, ".hook-state", "sessions", f)))["harness_session_id"] == "SK")
        kpost = lambda path, turn="k1": run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=kproj, env=kenv,
                                             inp=json.dumps({"session_id": "SK", "turn_id": turn, "hook_event_name": "PostToolUse", "tool_name": "Write",
                                                             "tool_use_id": f"u{abs(hash(path + open(os.path.join(kproj, path)).read())) % 99991}", "cwd": kproj,
                                                             "tool_input": {"file_path": os.path.join(kproj, path)}}))
        shardK = f".agents/workarea/events.{tK}.yaml"
        open(os.path.join(kproj, shardK), "w").write(ev("Evnt0005", "T002", "2026-09-01 10:00:00", "COMPLETED").replace("Xk9Qm2Ab", tK) + ev("Evnt0006", "T002", "2026-09-02 10:00:00", "OPEN").replace("Xk9Qm2Ab", tK))
        r0 = kpost(shardK)
        # move Evnt0005 by hand the right way: archive first, then remove
        open(os.path.join(kwa, "archive", "events.yaml"), "a").write(ev("Evnt0005", "T002", "2026-09-01 10:00:00", "COMPLETED").replace("Xk9Qm2Ab", tK))
        r1 = kpost(".agents/workarea/archive/events.yaml")
        open(os.path.join(kproj, shardK), "w").write(ev("Evnt0006", "T002", "2026-09-02 10:00:00", "OPEN").replace("Xk9Qm2Ab", tK))
        r2 = kpost(shardK)
        check("guard: archive-first move out of the own shard is accepted", r0.returncode == 0 and r1.returncode == 0 and r2.returncode == 0, r0.stderr[:200] + r1.stderr[:200] + r2.stderr[:200])
        open(os.path.join(kproj, shardK), "w").write("[]\n")
        r = kpost(shardK)
        check("guard: removing an unarchived entry is still blocked", r.returncode == 2 and "Evnt0006" in r.stderr and "archive/events.yaml" in r.stderr, r.stderr[:300])
        open(os.path.join(kproj, shardK), "w").write(ev("Evnt0006", "T002", "2026-09-02 10:00:00", "OPEN").replace("Xk9Qm2Ab", tK))
        kpost(shardK)
        arch_txt = open(os.path.join(kwa, "archive", "events.yaml")).read()
        open(os.path.join(kwa, "archive", "events.yaml"), "w").write(arch_txt.split("- Evnt0005:")[0])
        r = kpost(".agents/workarea/archive/events.yaml")
        check("guard: archives never lose an ID", r.returncode == 2 and "archive lost" in r.stderr and "Evnt0005" in r.stderr, r.stderr[:300])
        open(os.path.join(kwa, "archive", "events.yaml"), "w").write(arch_txt)
        kpost(".agents/workarea/archive/events.yaml")
        r = run([PY, ks, "ledger", "archive", "events", "--before", "2026-12-31"], cwd=kproj, env=kenv)
        r2 = run([PY, ks, "ledger", "archive", "events", "--before", "2026-12-31", "--force"], cwd=kproj, env=kenv)
        check("ks ledger archive refuses while a session is active, --force archives the shard's closed entries",
              r.returncode != 0 and "session" in r.stderr and r2.returncode == 0 and "Evnt0005" not in open(os.path.join(kproj, shardK)).read()
              and "Evnt0006" in open(os.path.join(kproj, shardK)).read(), r.stderr + r2.stdout + r2.stderr)
        r = run([PY, ks, "harness", "retrust"], cwd=kproj, env=kenv)
        r2 = run([PY, ks, "harness", "retrust", "--ack"], cwd=kproj, env=kenv)
        r3 = run([PY, ks, "harness", "retrust"], cwd=kproj, env=kenv)
        check("ks harness retrust: unknown → ack → clean", r.returncode == 1 and r2.returncode == 0 and r3.returncode == 0 and "no change" in r3.stdout, r.stdout + r3.stdout)
        r = run([PY, ks, "doctor"], cwd=kproj, env=kenv)
        check("ks doctor runs end to end", r.returncode == 0 and "== project" in r.stdout and "FAIL ·" in r.stdout, r.stdout[-300:] + r.stderr)
        check("ks doctor: no marketplace / plugin / trust recorded → three WARNs naming the step",
              "Codex marketplace: none" in r.stdout and "tksfw@tksfw: not installed" in r.stdout, r.stdout)
        # Codex ≥ 0.15x records the marketplace, the plugin and hook trust in config.toml — doctor must read those (2.4.1)
        dch = os.path.join(tmp, "codexhome_reg")
        os.makedirs(dch, exist_ok=True)
        hj = json.load(open(os.path.join(plug, "hooks", "hooks.json")))
        entries = [(ev, i, j) for ev, lst in hj["hooks"].items() for i, h in enumerate(lst) for j, _ in enumerate(h.get("hooks") or [])]
        state = "".join(f'[hooks.state."tksfw@tksfw:hooks/hooks.json:{ev.lower()}:{i}:{j}"]\ntrusted_hash = "sha256:00"\n\n' for ev, i, j in entries)
        with open(os.path.join(dch, "config.toml"), "w") as fh:
            fh.write(f'model = "gpt-5.6-sol"\nmodel_provider = "ibm"\n\n[model_providers.ibm]\nbase_url = "https://x"\n\n'
                     f'[marketplaces.tksfw]\nsource_type = "local"\nsource = "{os.path.dirname(os.path.dirname(plug))}"\n\n[plugins."tksfw@tksfw"]\nenabled = true\n\n{state}')
        renv = dict(kenv); renv["CODEX_HOME"] = dch
        r = run([PY, ks, "doctor"], cwd=kproj, env=renv)
        check("ks doctor reads [marketplaces], [plugins] and [hooks.state] from Codex config.toml",
              "Codex marketplace: `tksfw` →" in r.stdout and "tksfw@tksfw: enabled" in r.stdout and f"Codex hooks trusted: {len(entries)}/{len(entries)}" in r.stdout
              and "personal marketplace" not in r.stdout, r.stdout)
        with open(os.path.join(dch, "config.toml"), "a") as fh:
            fh.write('profile = "x"\nprofile = "y"\n')          # duplicate key → invalid TOML
        r = run([PY, ks, "doctor"], cwd=kproj, env=renv)
        check("ks doctor FAILs loudly when Codex config.toml does not parse", "does not parse" in r.stdout and "1 FAIL" in r.stdout or "FAIL" in r.stdout.split("\n")[-2], r.stdout[-400:])
        r = run([PY, ks, "dev", "test"], cwd=kproj, env=kenv)
        check("ks dev refuses to run from a plugin home", r.returncode != 0 and "checkout" in r.stderr, r.stderr)
        r = run([PY, os.path.join(REPO, "tools", "ks"), "self", "version"], env=kenv | {"TKSFW_HOME": REPO})
        check("ks from the checkout reports repo home", "repo at" in r.stdout, r.stdout)

        # 17 — live reconfiguration
        lproj = os.path.join(tmp, "live")
        run([PY, ks, "project", "init", lproj], cwd=tmp, env=kenv)
        seed_agents(lproj)
        lenv = kenv | {"TKSFW_USER": "carlos"}
        lhook = lambda script, extra, args=(): run([PY, os.path.join(plug, "hooks", script), *args], cwd=lproj, env=lenv,
                                                   inp=json.dumps({"session_id": "SL", "turn_id": "l1", "cwd": lproj, **extra}))
        lhook("inject_state.py", {"source": "startup"})
        r = lhook("track_edits.py", {"prompt": "hi"}, ["--phase", "prompt"])
        check("prompt notice silent when nothing changed", r.returncode == 0 and r.stdout.strip() == "", r.stdout)
        r = run([PY, ks, "routing", "use", "openrouter", "--force"], cwd=lproj, env=lenv)       # a session is active (3.4.0 guard)
        check("ks routing use prints the effect line", r.returncode == 0 and "next subagent spawn" in r.stdout, r.stdout + r.stderr)
        r = lhook("track_edits.py", {"prompt": "hi"}, ["--phase", "prompt"])
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
        check("prompt notice reports the routing switch", "routing.openrouter" in ctx and "was [routing.ibm-anthropic]" in ctx, r.stdout[:300])
        r = lhook("track_edits.py", {"prompt": "hi"}, ["--phase", "prompt"])
        check("prompt notice reported once", r.stdout.strip() == "", r.stdout)
        r = lhook("track_edits.py", {"prompt": "hi"}, ["--phase", "prompt"])   # operator change via env
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=lproj, env=lenv | {"TKSFW_USER": "bob"},
                inp=json.dumps({"session_id": "SL", "turn_id": "l2", "cwd": lproj, "prompt": "hi"}))
        check("prompt notice reports the operator change", "Operator now `bob`" in r.stdout, r.stdout[:300])
        # busy check
        lhook("subagent_track.py", {"hook_event_name": "SubagentStart", "agent_id": "z1", "agent_type": "x-builder"}, ["--start"])
        r = run([PY, ks, "routing", "use", "ibm-openai"], cwd=lproj, env=lenv)
        r2 = run([PY, ks, "routing", "use", "ibm-openai", "--force"], cwd=lproj, env=lenv)
        check("ks routing use refuses while a session is active / a subagent runs, --force overrides", r.returncode != 0 and ("subagent" in r.stderr or "session(s) active" in r.stderr) and r2.returncode == 0, r.stderr + r2.stderr)
        r = run([PY, ks, "project", "update"], cwd=lproj, env=lenv)
        check("ks project update refuses while the project is busy", r.returncode != 0 and ("session" in r.stderr or "subagent" in r.stderr), r.stderr)
        # external change notice (archive by ks)
        lwa = os.path.join(lproj, ".agents", "workarea")
        open(os.path.join(lwa, "tasks.md"), "w").write("# A\n- [x] T001 a - main : COMPLETED 2026-01-05 10:00:00 [ev:Evnt0001]\n# B\n- [ ] T002 b - main : OPEN 2026-01-06 10:00:00\n")
        lhook("track_edits.py", {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "lw1", "tool_input": {"file_path": os.path.join(lwa, "tasks.md")}})
        r = run([PY, ks, "ledger", "archive-plan"], cwd=lproj, env=lenv)
        check("ks ledger archive-plan prints the files effect", r.returncode == 0 and "files changed now" in r.stdout, r.stdout + r.stderr)
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=lproj, env=lenv | {"TKSFW_USER": "bob"},
                inp=json.dumps({"session_id": "SL", "turn_id": "l3", "cwd": lproj, "prompt": "hi"}))
        check("prompt notice lists files changed outside the session", "changed outside this session" in r.stdout and "tasks.md" in r.stdout, r.stdout[:400])
        # self setup
        shome = os.path.join(tmp, "setuphome")
        senv2 = kenv | {"HOME": shome, "CODEX_HOME": os.path.join(shome, ".codex")}
        os.makedirs(shome)
        r = run([PY, ks, "self", "setup", "--operator", "Carlos Veira"], env=senv2)
        r2 = run([PY, ks, "self", "setup", "--operator", "Carlos Veira"], env=senv2)
        ag = open(os.path.join(shome, ".codex", "AGENTS.md")).read()
        check("ks self setup appends both stanzas once", r.returncode == 0 and ag.count("TKSfw bootstrap stanza") == 1
              and os.path.isfile(os.path.join(shome, ".claude", "CLAUDE.md")) and "already present" in r2.stdout, r.stdout + r2.stdout + r.stderr)
        r = run([PY, ks, "doctor"], env=senv2, cwd=tmp)
        check("ks doctor sees the stanzas", "bootstrap stanza" in r.stdout and "present" in r.stdout, r.stdout[-400:])
        check("docs: getting-started, operations, ks present and cross-linked",
              all(os.path.isfile(os.path.join(REPO, "docs", f)) for f in ("getting-started.md", "operations.md", "ks.md"))
              and "getting-started.md" in open(os.path.join(REPO, "README.md")).read()
              and "ks self setup" in open(os.path.join(REPO, "docs", "getting-started.md")).read())

        # 19 — Excel export
        import zipfile, xml.etree.ElementTree as ET
        xout = os.path.join(tmp, "ledgers.xlsx")
        r = run([PY, ks, "ledger", "export", "all", "--out", xout, "--archive"], cwd=sproj, env=senv)
        check("ks ledger export all writes a workbook", r.returncode == 0 and os.path.isfile(xout) and "changes" in r.stdout, r.stdout + r.stderr)
        with zipfile.ZipFile(xout) as z:
            names = z.namelist()
            wbx = ET.fromstring(z.read("xl/workbook.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_names = [e.get("name") for e in wbx.findall(".//m:sheet", ns)]
            s1 = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
            ET.fromstring(z.read("xl/styles.xml")); ET.fromstring(z.read("[Content_Types].xml"))
        check("workbook parts parse and sheets are Summary + every kind",
              sheet_names == ["Summary", "changes", "lessons", "handoffs", "events", "decisions", "deliverables", "tasks"]
              and "xl/styles.xml" in names, str(sheet_names))
        rows = s1.findall(".//m:sheetData/m:row", ns)
        header = [t.text for t in rows[0].findall(".//m:t", ns)]
        check("changes sheet: header from schema + Session/Source/Archived, frozen pane, autofilter, one row per shard entry",
              header[:2] == ["EntryID", "AuthorAgent"] and header[-3:] == ["Session", "Source", "Archived"]
              and s1.find(".//m:pane", ns) is not None and s1.find(".//m:autoFilter", ns) is not None and len(rows) >= 5, str(header) + str(len(rows)))
        try:
            import openpyxl
            wbo = openpyxl.load_workbook(xout)
            ws = wbo["changes"]
            hdr = [c.value for c in ws[1]]
            ts_col = hdr.index("Timestamp") + 1
            import datetime as _dt
            check("openpyxl: timestamps are real datetimes, IDs text, memo wrap set",
                  isinstance(ws.cell(row=2, column=ts_col).value, _dt.datetime) and isinstance(ws.cell(row=2, column=1).value, str)
                  and ws.cell(row=2, column=hdr.index("Description") + 1).alignment.wrap_text is True, str(ws.cell(row=2, column=ts_col).value))
            wst = wbo["tasks"]
            th = [c.value for c in wst[1]]
            check("openpyxl: tasks sheet has Agent/Block/Level/Parent", all(x in th for x in ("Agent", "Block", "Level", "Parent")) and wst.max_row >= 2, str(th))
        except ImportError:
            print("[SKIP] openpyxl not available")
        r = run([PY, ks, "ledger", "export", "changes,events", "--out", os.path.join(tmp, "two.xlsx")], cwd=sproj, env=senv)
        with zipfile.ZipFile(os.path.join(tmp, "two.xlsx")) as z:
            wbx = ET.fromstring(z.read("xl/workbook.xml"))
            two = [e.get("name") for e in wbx.findall(".//m:sheet", ns)]
        check("export by category", r.returncode == 0 and two == ["Summary", "changes", "events"], str(two) + r.stderr)
        r = run([PY, ks, "ledger", "export", "changes", "--session", tA, "--csv", os.path.join(tmp, "csvout")], cwd=sproj, env=senv)
        csvtxt = open(os.path.join(tmp, "csvout", "changes.csv")).read()
        check("export --session --csv: only that session's entries, CSV written", r.returncode == 0 and "Aaaa1111" in csvtxt and "Bbbb2222" not in csvtxt, r.stdout + r.stderr)
        r = run([PY, ks, "ledger", "export", "bogus"], cwd=sproj, env=senv)
        check("export rejects an unknown kind", r.returncode != 0 and "unknown kind" in r.stderr, r.stderr)
        r = run([PY, ks, "ledger", "export", "all"], cwd=sproj, env=senv)
        check("default output lands under workarea/exports", r.returncode == 0 and os.path.isdir(os.path.join(wa, "exports")) and any(f.endswith(".xlsx") for f in os.listdir(os.path.join(wa, "exports"))), r.stdout + r.stderr)

        # 20 — project reset
        rproj = os.path.join(tmp, "resetp")
        os.makedirs(rproj)
        run(["git", "init", "-q"], cwd=rproj)
        run([PY, ks, "project", "init"], cwd=rproj, env=kenv)
        run(["git", "add", "-A"], cwd=rproj); run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=rproj)
        rwa = os.path.join(rproj, ".agents", "workarea")
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=rproj, env=kenv, inp=json.dumps({"session_id": "SR", "turn_id": "r1", "source": "startup", "cwd": rproj}))
        tR = next(json.load(open(os.path.join(rwa, ".hook-state", "sessions", f)))["token"] for f in os.listdir(os.path.join(rwa, ".hook-state", "sessions")))
        open(os.path.join(rwa, f"changes.{tR}.yaml"), "w").write(change_entry("Rrrr1111", tR, "carlos"))
        open(os.path.join(rwa, "tasks.md"), "w").write("# A\n- [ ] T001 a - main : OPEN 2026-09-07 10:00:00\n")
        os.makedirs(os.path.join(rwa, "archive")); open(os.path.join(rwa, "archive", "events.yaml"), "w").write("[]\n")
        open(os.path.join(rwa, "deliverables.yaml"), "w").write("- REPORT:\n    Title: \"r\"\n    Path: \"report-*.md\"\n")
        open(os.path.join(rproj, ".agents", "agents", "x-builder.toml"), "w").write('name = "x-builder"\ndescription = "d"\n')
        os.makedirs(os.path.join(rproj, ".codex", "agents")); open(os.path.join(rproj, ".codex", "agents", "x-builder.toml"), "w").write("# tksfw:mirror\n")
        run([PY, watool, "create", "x-builder", "T001", "--session", tR], cwd=rproj, env=kenv)
        run([PY, watool, "create", "x-builder", "T001", "--session", tR, "--worktree"], cwd=rproj, env=kenv)
        wtd = os.path.join(rproj, ".agents", "worktrees", f"x-builder--{tR}.T001.0")
        open(os.path.join(wtd, "w.txt"), "w").write("w\n"); run(["git", "add", "w.txt"], cwd=wtd); run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "w"], cwd=wtd)
        r = run([PY, ks, "project", "reset", "--dry-run"], cwd=rproj, env=kenv)
        check("reset --dry-run plans and changes nothing", r.returncode == 0 and "dry run" in r.stdout and "ledgers" in r.stdout and os.path.isfile(os.path.join(rwa, f"changes.{tR}.yaml")), r.stdout + r.stderr)
        r = run([PY, ks, "project", "reset", "--yes"], cwd=rproj, env=kenv)
        check("reset refuses while a session is active", r.returncode != 0 and "session" in r.stderr, r.stderr)
        for f in os.listdir(os.path.join(rwa, ".hook-state", "sessions")):
            d = json.load(open(os.path.join(rwa, ".hook-state", "sessions", f))); d["last_seen"] = 0; json.dump(d, open(os.path.join(rwa, ".hook-state", "sessions", f), "w"))
        r = run([PY, ks, "project", "reset", "--archive"], cwd=rproj, env=kenv)
        check("reset refuses without --yes when not interactive", r.returncode != 0 and "--yes" in r.stderr, r.stderr)
        r = run([PY, ks, "project", "reset", "--yes"], cwd=rproj, env=kenv)
        check("reset refuses to delete an unmerged worktree branch without --force", r.returncode != 0 and "unmerged" in r.stderr, r.stderr)
        r = run([PY, ks, "project", "reset", "--archive", "--label", "phase 1", "--yes"], cwd=rproj, env=kenv)
        hist = glob.glob(os.path.join(rproj, ".agents", "history", "*-phase_1"))
        check("reset --archive moves ledgers, plan, archives, agents to history and records the generation",
              r.returncode == 0 and len(hist) == 1 and os.path.isfile(os.path.join(hist[0], "workarea", f"changes.{tR}.yaml"))
              and os.path.isfile(os.path.join(hist[0], "workarea", "tasks.md")) and os.path.isfile(os.path.join(hist[0], "workarea", "archive", "events.yaml"))
              and os.path.isfile(os.path.join(hist[0], "agents", "x-builder.toml"))
              and not os.path.exists(os.path.join(rwa, f"changes.{tR}.yaml")) and not os.path.exists(os.path.join(rwa, ".hook-state"))
              and os.path.isfile(os.path.join(rwa, "deliverables.yaml")) and not os.path.exists(os.path.join(rproj, ".codex", "agents", "x-builder.toml"))
              and not os.path.exists(wtd) and json.load(open(os.path.join(rproj, ".agents", ".tksfw.json")))["resets"][0]["mode"] == "archive",
              r.stdout + r.stderr)
        br = run(["git", "branch", "--list", "agent/*"], cwd=rproj, capture_output=True, text=True) if False else run(["git", "branch", "--list", "agent/*"], cwd=rproj)
        check("--archive keeps the worktree branch", "agent/x-builder" in br.stdout, br.stdout)
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=rproj, env=kenv, inp=json.dumps({"session_id": "SR2", "turn_id": "r2", "source": "startup", "cwd": rproj}))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
        rs = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=rproj, env=kenv)
        check("next session and STATE.md announce generation 2", "Generation 2" in ctx and "history/" in ctx and "Generation 2" in rs.stdout, ctx[:300] + rs.stdout[:200])
        probe = "import sys; sys.path.insert(0, %r); import hooklib as H; print(H.classify('.agents/history/x/workarea/tasks.md'))"
        r = run([PY, "-c", probe % os.path.join(plug, "hooks")], cwd=rproj, env=kenv)
        check(".agents/history/ is never watched", r.stdout.strip() == "None", r.stdout)
        # clear mode with --keep-agents and --registry
        open(os.path.join(rproj, ".agents", "agents", "y-writer.toml"), "w").write('name = "y-writer"\ndescription = "d"\n')
        tR2 = next(json.load(open(os.path.join(rwa, ".hook-state", "sessions", f)))["token"] for f in os.listdir(os.path.join(rwa, ".hook-state", "sessions")))
        open(os.path.join(rwa, f"lessons.{tR2}.yaml"), "w").write("[]\n")
        for f in os.listdir(os.path.join(rwa, ".hook-state", "sessions")):
            d = json.load(open(os.path.join(rwa, ".hook-state", "sessions", f))); d["last_seen"] = 0; json.dump(d, open(os.path.join(rwa, ".hook-state", "sessions", f), "w"))
        r = run([PY, ks, "project", "reset", "--keep-agents", "--registry", "--yes"], cwd=rproj, env=kenv)
        check("clear reset: ledgers deleted, agents kept, registry cleared, generation 3",
              r.returncode == 0 and not os.path.exists(os.path.join(rwa, f"lessons.{tR2}.yaml")) and os.path.isfile(os.path.join(rproj, ".agents", "agents", "y-writer.toml"))
              and not os.path.exists(os.path.join(rwa, "deliverables.yaml")) and len(json.load(open(os.path.join(rproj, ".agents", ".tksfw.json")))["resets"]) == 2
              and "generation 3" in r.stdout, r.stdout + r.stderr)
        r = run([PY, home_np := os.path.join(work, "tools", "new_project.py"), rproj, "--update"], cwd=rproj, env=kenv)
        check("project update preserves the resets record", len(json.load(open(os.path.join(rproj, ".agents", ".tksfw.json"))).get("resets", [])) == 2, r.stdout + r.stderr)

        # 21 — ledger digest
        dgp = os.path.join(tmp, "digestp")
        run([PY, ks, "project", "init", dgp], cwd=tmp, env=kenv)
        dwa = os.path.join(dgp, ".agents", "workarea")
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=dgp, env=kenv, inp=json.dumps({"session_id": "SD", "turn_id": "d1", "source": "startup", "cwd": dgp}))
        tD = next(json.load(open(os.path.join(dwa, ".hook-state", "sessions", f)))["token"] for f in os.listdir(os.path.join(dwa, ".hook-state", "sessions")))
        own = f"    OwnerSessionId: {tD}\n    OwnerSessionUserName: carlos\n"
        def evd(i, task, ts, et, st, title, extra=""):
            return f"- {i}:\n    TaskID: {task}\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"{ts}\"\n{own}    EventType: {et}\n{extra}    Title: \"{title}\"\n    Remarks: |-\n      x\n    Status: {st}\n"
        open(os.path.join(dwa, f"events.{tD}.yaml"), "w").write(
            evd("Evis0001", "T001", "2026-09-07 09:00:00", "ISSUE", "OPEN", "MCP times out") +
            evd("Evrv0001", "T002", "2026-09-07 09:30:00", "REVIEW", "FAIL", "Review failed: missing sources") +
            evd("Evts0001", "T003", "2026-09-07 09:40:00", "TEST", "KO", "Test KO") +
            evd("Evts0002", "T003", "2026-09-07 09:50:00", "TEST", "OK", "Test OK after fix") +
            evd("Evdc0001", "N/A", "2026-09-07 10:00:00", "DECISION", "ACCEPTED", "Accept archive layout", "    DecisionID: Dcsn0001\n"))
        def decd(i, title, status, scope):
            return good_dec.replace("Tstdec01", i).replace('"Fixture decision (valid)"', f'"{title}"').replace("Status: ACCEPTED", f"Status: {status}").replace("      Tests only.", f"      {scope}").replace('    LastUpdate: "2026-07-21 10:00:00"\n', '    LastUpdate: "2026-09-07 09:00:00"\n' + own)
        open(os.path.join(dwa, f"decisions.{tD}.yaml"), "w").write(decd("Dcsn0001", "One archive per ledger", "OPEN", "Ledger layout") + decd("Dcsn0002", "Terra for builders", "OPEN", "Routing"))
        open(os.path.join(dwa, f"handoffs.{tD}.yaml"), "w").write(f"- Hnd00001-BEGIN:\n    EventID: N/A\n    TaskID: T002\n    AuthorAgent: main\n    TargetAgent: report-writer\n    Timestamp: \"2026-09-07 09:20:00\"\n{own}    Title: \"Draft section 3\"\n    Description: |-\n      Write section 3; cite every figure.\n    Scope: sections/03.md\n    Inputs: |-\n      - sources/*.md\n      - Dcsn0001\n    Outputs: |-\n      - sections/03.md\n")
        open(os.path.join(dwa, f"lessons.{tD}.yaml"), "w").write(f"- Lssn0001:\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"2026-09-07 08:00:00\"\n{own}    Title: \"Cite the source next to each figure\"\n    Description: |-\n      Reviewer rejected unsourced figures twice.\n    Remarks: |-\n      x\n")
        open(os.path.join(dwa, "tasks.md"), "w").write("# Phase 1\n- [ ] T001 Fetch sources - sources-researcher : IN-PROGRESS 2026-09-07 09:00:00\n- [ ] T002 Draft report - report-writer : IN-PROGRESS 2026-09-07 09:20:00\n- [x] T003 Integration test - x-builder : COMPLETED 2026-09-07 09:50:00 [ev:Evts0002]\n")
        rs = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=dgp, env=kenv)
        st = rs.stdout
        check("STATE.md digest: blocked gate T002 only (T003 recovered), decision in force via event, pending, issue, in-flight handoff, lesson",
              "## Ledger digest" in st and "task T002: REVIEW FAIL" in st and "T003" not in st.split("Blocked gates")[1].split("###")[0]
              and "Dcsn0001" in st.split("Decisions in force")[1].split("###")[0] and "Dcsn0002" in st.split("Pending decisions")[1].split("###")[0]
              and "Evis0001" in st and "Hnd00001-BEGIN" in st and "Lssn0001" in st, st[-1500:])
        check("STATE.md stays under the injection budget", len(st) < 9000, str(len(st)))
        r = run([PY, ks, "ledger", "digest", "--task", "T002"], cwd=dgp, env=kenv)
        check("ks ledger digest --task shows the task line, evidence chain and only T002 items",
              r.returncode == 0 and "### Task T002" in r.stdout and "Evidence chain: Evrv0001" in r.stdout and "Evis0001" not in r.stdout and "Hnd00001-BEGIN" in r.stdout, r.stdout + r.stderr)
        r = run([PY, ks, "ledger", "digest", "--json"], cwd=dgp, env=kenv)
        check("ks ledger digest --json", r.returncode == 0 and json.loads(r.stdout)["blocked"][0]["task"] == "T002", r.stdout[:200])
        r = run([PY, os.path.join(plug, "hooks", "subagent_track.py"), "--start"], cwd=dgp, env=kenv,
                inp=json.dumps({"session_id": "SD", "turn_id": "d1", "hook_event_name": "SubagentStart", "agent_id": "sub1", "agent_type": "report-writer", "cwd": dgp}))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
        check("SubagentStart briefing: own handoff, task evidence, blocked gate, in-force decision, lesson; under budget",
              "Your handoff: Hnd00001-BEGIN" in ctx and "Inputs: sources/*.md; Dcsn0001" in ctx and "REVIEW FAIL" in ctx
              and "Dcsn0001" in ctx.split("Decisions in force")[1] and "Lssn0001" in ctx and len(ctx) <= 4200, ctx[:600])
        r = run([PY, os.path.join(plug, "hooks", "subagent_track.py"), "--start"], cwd=dgp, env=kenv,
                inp=json.dumps({"session_id": "SD", "turn_id": "d1", "hook_event_name": "SubagentStart", "agent_id": "sub2", "agent_type": "sources-researcher", "cwd": dgp}))
        ctx2 = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
        check("briefing without an open handoff still carries global context", "Decisions in force" in ctx2 and "Your handoff" not in ctx2, ctx2[:300])
        # prompt notice: new issue + failed gate appended during the session
        run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=dgp, env=kenv, inp=json.dumps({"session_id": "SD", "turn_id": "d2", "cwd": dgp, "prompt": "x"}))
        open(os.path.join(dwa, f"events.{tD}.yaml"), "a").write(evd("Evis0002", "T002", "2026-09-07 11:00:00", "ISSUE", "OPEN", "Source list incomplete") + evd("Evau0001", "T001", "2026-09-07 11:10:00", "AUDIT", "NON-CONFORMANT", "Audit failed"))
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=dgp, env=kenv, inp=json.dumps({"session_id": "SD", "turn_id": "d3", "cwd": dgp, "prompt": "x"}))
        check("prompt notice announces the new open issue and the failed gate", "New open issue Evis0002" in r.stdout and "Gate failed: AUDIT NON-CONFORMANT" in r.stdout, r.stdout[:400])
        # [state] limits honoured
        mt = os.path.join(dgp, ".agents", "config.toml")
        open(mt, "a").write("\n")
        txt = open(mt).read().replace("issues = 10", "issues = 1")
        open(mt, "w").write(txt)
        r = run([PY, ks, "ledger", "digest"], cwd=dgp, env=kenv)
        check("[state] limits honoured (issues = 1 → '… 1 more')", "… 1 more" in r.stdout.split("Open issues")[1].split("###")[0], r.stdout)
        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md carries the consult-before-deciding rule", "Consult before deciding" in agents_md and "SUPERSEDED" in agents_md)

        # 22 — Human in the Loop
        hp = os.path.join(tmp, "hilp")
        run([PY, ks, "project", "init", hp], cwd=tmp, env=kenv)
        hwa = os.path.join(hp, ".agents", "workarea")
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=hp, env=kenv, inp=json.dumps({"session_id": "SH", "turn_id": "h1", "source": "startup", "cwd": hp}))
        tH = next(json.load(open(os.path.join(hwa, ".hook-state", "sessions", f)))["token"] for f in os.listdir(os.path.join(hwa, ".hook-state", "sessions")))
        ownH = f"    OwnerSessionId: {tH}\n    OwnerSessionUserName: carlos\n"
        def dech(i, title, status, imp, rev, conf, author="main"):
            return (good_dec.replace("Tstdec01", i).replace('"Fixture decision (valid)"', f'"{title}"').replace("Status: ACCEPTED", f"Status: {status}")
                    .replace("Impact: LOW", f"Impact: {imp}").replace("Reversibility: EASY", f"Reversibility: {rev}").replace("ConfirmationType: AUTO-MODE", f"ConfirmationType: {conf}")
                    .replace("AuthorAgent: main", f"AuthorAgent: {author}").replace('    LastUpdate: "2026-07-21 10:00:00"\n', '    LastUpdate: "2026-09-07 09:00:00"\n' + ownH))
        hshard = os.path.join(hwa, f"decisions.{tH}.yaml")
        def hook_write(content, ids):
            open(hshard, "w").write(content)
            return run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=hp, env=kenv,
                       inp=json.dumps({"session_id": "SH", "turn_id": "h2", "hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": hp,
                                       "tool_input": {"file_path": hshard, "content": content}}))
        r = run([PY, ks, "hil", "show"], cwd=hp, env=kenv)
        check("ks hil show: default HIGH or HARD, enforce", "Impact >= HIGH OR Reversibility >= HARD (enforce)" in r.stdout, r.stdout)
        e101_bad = dech("Dcsn0101", "ZFS everywhere", "OPEN", "VERY HIGH", "VERY HARD", "AUTO-MODE")
        e101 = dech("Dcsn0101", "ZFS everywhere", "OPEN", "VERY HIGH", "VERY HARD", "OPERATOR")
        e102_bad = dech("Dcsn0102", "Worker accepted", "ACCEPTED", "HIGH", "HARD", "OPERATOR", "x-builder")
        e102 = dech("Dcsn0102", "Worker accepted", "OPEN", "HIGH", "HARD", "OPERATOR", "x-builder")
        e103 = dech("Dcsn0103", "Escalated", "OPEN", "HIGH", "HARD", "OPERATOR", "x-builder")
        e104 = dech("Dcsn0104", "Small call", "ACCEPTED", "MEDIUM", "EASY", "AUTO-MODE")
        e104_or = dech("Dcsn0110", "High but easy", "ACCEPTED", "HIGH", "EASY", "AUTO-MODE")
        r = hook_write(e101_bad, ["Dcsn0101"])
        check("hook rejects a new above-threshold AUTO-MODE decision", r.returncode == 2 and "ConfirmationType must be OPERATOR" in r.stderr, r.stderr[:300])
        r = hook_write(e101 + e102_bad, ["Dcsn0102"])
        check("hook rejects an above-threshold decision accepted by a Worker (fixed entry in place passes)", r.returncode == 2 and "must stay OPEN" in r.stderr and "Dcsn0101" not in r.stderr, r.stderr[:300])
        r = hook_write(e101 + e102 + e103 + e104, ["Dcsn0103", "Dcsn0104"])
        check("compliant entries pass: Worker OPEN/OPERATOR above threshold; MEDIUM/EASY AUTO-MODE below", r.returncode == 0, r.stderr[:300])
        r = hook_write(e101 + e102 + e103 + e104 + e104_or, ["Dcsn0110"])
        check("OR default: HIGH/EASY AUTO-MODE is above threshold and rejected", r.returncode == 2 and "ConfirmationType must be OPERATOR" in r.stderr, r.stderr[:300])
        e110 = dech("Dcsn0110", "High but easy", "OPEN", "HIGH", "EASY", "OPERATOR")
        r = hook_write(e101 + e102 + e103 + e104 + e110, ["Dcsn0110"])
        check("the same entry fixed in place (OPEN/OPERATOR) passes", r.returncode == 0, r.stderr[:300])
        base = e101 + e102 + e103 + e104 + e110
        # legacy (not new) entries only warn
        base += dech("Dcsn0105", "Old big call", "ACCEPTED", "VERY HIGH", "VERY HARD", "AUTO-MODE")
        open(hshard, "w").write(base)
        r = run([PY, os.path.join(plug, "skills", "yaml-log-entry", "assets", "validate_yaml_log.py"), hshard], cwd=hp, env=kenv)
        check("validator without --hil-ids: existing entries warn, file still OK", r.returncode == 0 and "WARN" in r.stdout and "Dcsn0105" in r.stdout, r.stdout[:300])
        # advisory mode + OR logic via ks hil set; prompt notice reports the change
        run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=hp, env=kenv, inp=json.dumps({"session_id": "SH", "turn_id": "h3", "cwd": hp, "prompt": "x"}))
        r = run([PY, ks, "hil", "set", "--mode", "advisory", "--logic", "or", "--impact", "medium"], cwd=hp, env=kenv)
        check("ks hil set validates, rewrites [hil] and prints the effect line", r.returncode == 0 and "Impact >= MEDIUM OR Reversibility >= HARD (advisory)" in r.stdout and "→ applies to the next decision entry" in r.stdout, r.stdout)
        import tomllib as _tl
        hil_tbl = _tl.load(open(os.path.join(hp, ".agents", "config.toml"), "rb"))["hil"]
        check("[hil] table rewritten in place and config.toml still parses", hil_tbl == {"impact": "MEDIUM", "reversibility": "HARD", "logic": "or", "mode": "advisory"}, str(hil_tbl))
        r = run([PY, ks, "hil", "set", "--impact", "bogus"], cwd=hp, env=kenv)
        check("ks hil set rejects a bad level", r.returncode != 0 and "not in" in r.stderr + r.stdout, r.stderr)
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=hp, env=kenv, inp=json.dumps({"session_id": "SH", "turn_id": "h4", "cwd": hp, "prompt": "x"}))
        check("prompt notice announces the HIL change", "HIL threshold now Impact >= MEDIUM OR Reversibility >= HARD (advisory)" in r.stdout and "was Impact >= HIGH OR" in r.stdout, r.stdout[:400])
        base += dech("Dcsn0106", "Medium call", "ACCEPTED", "MEDIUM", "EASY", "AUTO-MODE")
        r = hook_write(base, ["Dcsn0106"])
        check("advisory mode: above-threshold (OR, MEDIUM) AUTO-MODE decision is warned, not rejected", r.returncode == 0, r.stderr[:300])
        r = run([PY, ks, "hil", "set", "--mode", "enforce"], cwd=hp, env=kenv)
        base += dech("Dcsn0107", "Medium call 2", "ACCEPTED", "MEDIUM", "EASY", "AUTO-MODE")
        r = hook_write(base, ["Dcsn0107"])
        check("back to enforce with OR/MEDIUM: rejected", r.returncode == 2, r.stderr[:200])
        base += dech("Dcsn0108", "Needs the operator", "OPEN", "VERY HIGH", "VERY HARD", "OPERATOR") + dech("Dcsn0109", "Fine", "OPEN", "LOW", "EASY", "AUTO-MODE")
        open(hshard, "w").write(base)
        r = run([PY, ks, "ledger", "digest"], cwd=hp, env=kenv)
        pend = r.stdout.split("Pending decisions")[1].split("###")[0]
        check("digest marks the pending HIL decision and not the small one", "Dcsn0108" in pend and "NEEDS OPERATOR CONFIRMATION (HIL)" in pend.split("Dcsn0108")[1].split("\n")[0] and "NEEDS OPERATOR" not in pend.split("Dcsn0109")[1].split("\n")[0], pend)
        r = run([PY, ks, "doctor"], cwd=hp, env=kenv)
        check("ks doctor shows the HIL threshold", "HIL threshold: Impact >= MEDIUM OR Reversibility >= HARD (enforce)" in r.stdout, r.stdout[-600:])
        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md has the Human in the Loop section with the default and the Worker rule",
              "### Human in the Loop" in agents_md and "`Impact ≥ HIGH` **or** `Reversibility ≥ HARD`" in agents_md and "Workers never accept" in agents_md and "§ Human in the Loop" in agents_md)

        # .claude/settings.json (2.6.0): Claude Code twin of the Codex permission profile, in both modes
        for _mode, _proj in (("plugin", ip_probe := os.path.join(tmp, "clprobe")), ("full", os.path.join(tmp, "clprobe_full"))):
            run([PY, ks, "project", "init", _proj] + (["--full"] if _mode == "full" else []), cwd=tmp, env=kenv)
            cs = json.load(open(os.path.join(_proj, ".claude", "settings.json")))
            check(f".claude/settings.json installed in {_mode} mode with the deny rules" + (" and hooks (sync_harness kept the other keys)" if _mode == "full" else ""),
                  cs["permissions"]["deny"] == ["Read(./_archive/**)", "Read(./_backup/**)"] and (_mode == "plugin" or cs.get("hooks")), json.dumps(cs)[:300])

        # .codex/config.toml (2.5.1): permission-profile syntax Codex 0.15x accepts — no bare relative keys
        import tomllib as _tl2
        cc = _tl2.load(open(os.path.join(REPO, "template", ".codex", "config.toml"), "rb"))
        fs = cc["permissions"][cc["default_permissions"]]["filesystem"]
        bare = [k for k in fs if not (os.path.isabs(k) or k.startswith("~") or k.startswith(":"))]
        check("template .codex/config.toml: filesystem keys are absolute, ~/ or :tokens; deny rules under :workspace_roots; extends :workspace",
              not bare and fs[":workspace_roots"].get("_archive/**") == "deny" and cc["permissions"]["hardened"].get("extends") == ":workspace"
              and "none" not in json.dumps(fs), str(fs))

        # 23 — install log and post-init guidance
        ip = os.path.join(tmp, "instp")
        r = run([PY, ks, "project", "init", ip], cwd=tmp, env=kenv)
        check("post-init: 'Recorded: install of v…' and plugin-mode next steps (no re-trust, ks doctor)",
              "Recorded: install of v" in r.stdout and "nothing to write by hand" in r.stdout and "Next steps" in r.stdout
              and "nothing to re-trust for this project" in r.stdout and "Record the install/update" not in r.stdout, r.stdout)
        man = json.load(open(os.path.join(ip, ".agents", ".tksfw.json")))
        check("manifest installs[0] = init/plugin with operator and version", man["installs"][0]["action"] == "init" and man["installs"][0]["mode"] == "plugin"
              and man["installs"][0]["version"] == open(os.path.join(REPO, "VERSION")).read().strip() and man["installs"][0]["operator"], str(man.get("installs")))
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=ip, env=kenv, inp=json.dumps({"session_id": "SI", "turn_id": "i1", "source": "startup", "cwd": ip}))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        check("SessionStart on a fresh project: install line asks the model to log the install (Layer METHOD)", "TKSfw installed v" in ctx and "Layer METHOD" in ctx, ctx[:400])
        tI = next(json.load(open(os.path.join(ip, ".agents", "workarea", ".hook-state", "sessions", f)))["token"] for f in os.listdir(os.path.join(ip, ".agents", "workarea", ".hook-state", "sessions")))
        open(os.path.join(ip, ".agents", "workarea", f"changes.{tI}.yaml"), "w").write(
            f"- Chng0001:\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"2099-01-01 00:00:00\"\n    OwnerSessionId: {tI}\n    OwnerSessionUserName: carlos\n    Layer: METHOD\n    Title: \"TKSfw installed\"\n    Description: |-\n      x\n    Files: |-\n      - .agents/.tksfw.json\n    Remarks: |-\n      x\n")
        r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=ip, env=kenv, inp=json.dumps({"session_id": "SI", "turn_id": "i2", "source": "resume", "cwd": ip}))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
        check("install line disappears once a METHOD-layer change is logged", "not yet recorded" not in ctx, ctx[:300])
        r = run([PY, ks, "project", "update", ip, "--force"], cwd=tmp, env=kenv)      # the test session above is still "active"
        man = json.load(open(os.path.join(ip, ".agents", ".tksfw.json")))
        check("project update appends installs[1] = update and says 'Recorded: update of v…'", len(man["installs"]) == 2 and man["installs"][1]["action"] == "update" and "Recorded: update of v" in r.stdout, r.stdout[-300:])
        fp2 = os.path.join(tmp, "instfull")
        r = run([PY, ks, "project", "init", fp2, "--full"], cwd=tmp, env=kenv)
        check("post-init in full mode: /hooks trust + retrust --ack steps", "type /hooks and trust them" in r.stdout and "ks harness retrust --ack" in r.stdout, r.stdout[-600:])

        # 24 — config.toml, routing tables, ks routing list, ks help
        cp3 = os.path.join(tmp, "cfg3")
        run([PY, ks, "project", "init", cp3], cwd=tmp, env=kenv)
        check("project ships .agents/config.toml (no models.toml)", os.path.isfile(os.path.join(cp3, ".agents", "config.toml")) and not os.path.exists(os.path.join(cp3, ".agents", "models.toml")))
        r = run([PY, ks, "routing", "list"], cwd=cp3, env=kenv)
        check("ks routing list: four tables, ibm-anthropic active via match, ibm-anthropic-cc marked default, models per tier",
              r.returncode == 0 and "5 routing table(s)" in r.stdout and "ibm-anthropic     [active (codex model_provider (match))]" in r.stdout and "gpt-5.6-sol[1m]" in r.stdout
              and "ibm-anthropic-cc  [default]" in r.stdout and "claude-sonnet-5[1m]" in r.stdout and "gpt-5.6-terra" in r.stdout
              and "google/gemini-flash-latest" in r.stdout and "anthropic/claude-opus-latest" in r.stdout and "match: codex_model_provider=ibm" in r.stdout, r.stdout)
        bad = open(os.path.join(cp3, ".agents", "config.toml")).read().replace('default_routing = "ibm-anthropic-cc"', 'default_routing = "nope"')
        open(os.path.join(cp3, ".agents", "config.toml.bad"), "w").write(bad)
        r = run([PY, os.path.join(plug, "hooks", "route_model.py"), "--check"], cwd=cp3, env=kenv | {"TKSFW_MODELS_FILE": os.path.join(cp3, ".agents", "config.toml.bad")})
        check("routing check rejects a default_routing that names no table", r.returncode != 0 and "default_routing = 'nope' names no" in r.stdout, r.stdout)
        os.remove(os.path.join(cp3, ".agents", "config.toml.bad"))
        r = run([PY, ks, "routing", "use", "ibm-anthropic-cc"], cwd=cp3, env=kenv)
        r = run([PY, ks, "routing", "list"], cwd=cp3, env=kenv)
        check("ks routing list marks the pinned table", "ibm-anthropic-cc  [pinned, default, active (selected (config.toml))]" in r.stdout, r.stdout)
        r = run([PY, ks, "routing", "resolve", "x-builder"], cwd=cp3, env=kenv)
        check("resolve under the pinned anthropic-cc table gives the 1M sonnet", "claude-sonnet-5[1m]" in r.stdout, r.stdout)
        run([PY, ks, "routing", "use", "ibm-openai-cc"], cwd=cp3, env=kenv)
        r = run([PY, ks, "routing", "resolve", "x-builder"], cwd=cp3, env=kenv)
        check("ibm-openai-cc: 1M gpt-5.6-terra for Claude Code", '"gpt-5.6-terra[1m]"' in r.stdout, r.stdout)
        run([PY, ks, "routing", "use", "ibm-anthropic-cc"], cwd=cp3, env=kenv)
        # legacy file name: readers accept models.toml; update renames it and keeps the pin
        os.replace(os.path.join(cp3, ".agents", "config.toml"), os.path.join(cp3, ".agents", "models.toml"))
        r = run([PY, ks, "routing", "show"], cwd=cp3, env=kenv)
        check("legacy .agents/models.toml is still read", "routing='ibm-anthropic-cc'" in r.stdout and "models.toml" in r.stdout, r.stdout)
        r = run([PY, ks, "project", "update", cp3, "--force"], cwd=tmp, env=kenv)
        check("ks project update renames models.toml → config.toml keeping the operator's content (pin survives)",
              "renamed: .agents/models.toml → .agents/config.toml" in r.stdout and os.path.isfile(os.path.join(cp3, ".agents", "config.toml"))
              and not os.path.exists(os.path.join(cp3, ".agents", "models.toml")) and 'selected = "ibm-anthropic-cc"' in open(os.path.join(cp3, ".agents", "config.toml")).read(), r.stdout)
        r = run([PY, ks, "help"], cwd=cp3, env=kenv)
        r2 = run([PY, ks, "help", "routing"], cwd=cp3, env=kenv)
        r3 = run([PY, ks, "ledger", "--help"], cwd=cp3, env=kenv)
        r4 = run([PY, ks, "help", "bogus"], cwd=cp3, env=kenv)
        check("ks help lists commands; ks help routing / ks ledger --help print the guides; unknown → error",
              "Run `ks help <command>`" in r.stdout and "ks routing list" in r2.stdout and "Selection order at spawn" in r2.stdout
              and "ks ledger digest" in r3.stdout and r4.returncode != 0, r.stdout[-200:] + r2.stdout[:200])
        for c in ("self", "operator", "project", "routing", "hil", "layers", "ledger", "harness", "doctor", "dev"):
            rr = run([PY, ks, "help", c], cwd=cp3, env=kenv)
            if rr.returncode != 0 or f"ks {c}" not in rr.stdout:
                check(f"ks help {c}", False, rr.stdout + rr.stderr)
                break
        else:
            check("ks help has a guide for every command", True)

        # 25 — main-session model
        mp5 = os.path.join(tmp, "mainm")
        r = run([PY, ks, "project", "init", mp5], cwd=tmp, env=kenv)
        sl = os.path.join(mp5, ".claude", "settings.local.json")
        cc = open(os.path.join(mp5, ".codex", "config.toml")).read()
        check("init writes the main-session model: Claude Code → claude-opus-5[1m] (default table), Codex → claude-opus-5 (provider match)",
              "Claude Code main session → claude-opus-5[1m]" in r.stdout and json.load(open(sl))["model"] == "claude-opus-5[1m]"
              and 'model = "claude-opus-5"' in cc and 'model_reasoning_effort = "high"' in cc, r.stdout[-600:])
        import tomllib as _tl3
        _tl3.loads(cc)
        r = run([PY, ks, "routing", "use", "ibm-openai-cc"], cwd=mp5, env=kenv)
        cc = open(os.path.join(mp5, ".codex", "config.toml")).read()
        check("routing use rewrites both main-session models and says how to switch now",
              json.load(open(sl))["model"] == "gpt-5.6-sol[1m]" and 'model = "gpt-5.6-sol[1m]"' in cc and cc.count("model_reasoning_effort") == 1
              and "now: `/model gpt-5.6-sol[1m]`" in r.stdout, r.stdout + cc)
        envm = json.load(open(sl)).get("env", {})
        check("routing use writes the Claude Code alias map (ANTHROPIC_DEFAULT_*_MODEL) for third-party ids",
              envm == {"ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.6-luna[1m]", "ANTHROPIC_DEFAULT_SONNET_MODEL": "gpt-5.6-terra[1m]", "ANTHROPIC_DEFAULT_OPUS_MODEL": "gpt-5.6-sol[1m]"}
              and "subagent aliases → haiku→gpt-5.6-luna[1m]" in r.stdout, json.dumps(envm) + r.stdout[-400:])
        # agent mirrors re-rendered on routing use (plugin mode) with the full routed id in Claude frontmatter
        open(os.path.join(mp5, ".agents", "agents", "cv-writer.toml"), "w").write('name = "cv-writer"\ndescription = "MUST BE USED for writing CVs."\ndeveloper_instructions = "Write."\n')
        r = run([PY, ks, "routing", "use", "ibm-anthropic-cc", "--force"], cwd=mp5, env=kenv)
        cm = os.path.join(mp5, ".claude", "agents", "cv-writer.md")
        check("routing use re-renders agent mirrors in plugin mode; Claude frontmatter carries the routed id",
              os.path.isfile(cm) and "model: claude-sonnet-5[1m]" in open(cm).read() and "Agent mirrors re-rendered" in r.stdout, r.stdout[-300:] + (open(cm).read() if os.path.isfile(cm) else ""))
        r = run([PY, ks, "routing", "use", "ibm-openai-cc", "--force"], cwd=mp5, env=kenv)
        _tl3.loads(cc)
        r = run([PY, ks, "project", "update", mp5, "--force"], cwd=tmp, env=kenv)
        cc = open(os.path.join(mp5, ".codex", "config.toml")).read()
        check("project update classifies .codex/config.toml as pristine despite the model lines and keeps them",
              ".codex/config.toml" not in (r.stdout.split("kept (edited locally)")[1].split("unchanged")[0] if "kept (edited locally)" in r.stdout else "")
              and 'model = "gpt-5.6-sol[1m]"' in cc and 'default_permissions = "hardened"' in cc, r.stdout)
        r = run([PY, os.path.join(plug, "hooks", "route_model.py"), "--main"], cwd=mp5, env=kenv)
        mm = json.loads(r.stdout)
        check("route_model --main reports the judge tier per harness", mm["claude"]["model"] == "gpt-5.6-sol[1m]" and mm["codex"]["routing"] == "ibm-openai-cc", r.stdout)
        # prompt notice after a routing change names the main-session switch
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=mp5, env=kenv, inp=json.dumps({"session_id": "SM", "turn_id": "m1", "source": "startup", "cwd": mp5}))
        run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=mp5, env=kenv, inp=json.dumps({"session_id": "SM", "turn_id": "m2", "cwd": mp5, "prompt": "x"}))
        run([PY, ks, "routing", "use", "ibm-anthropic-cc", "--force"], cwd=mp5, env=kenv)
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=mp5, env=kenv, inp=json.dumps({"session_id": "SM", "turn_id": "m3", "cwd": mp5, "prompt": "x"}))
        check("prompt notice: routing switch + main-session /model instruction", "Model routing now [routing.ibm-anthropic-cc]" in r.stdout and "/model claude-opus-5[1m]" in r.stdout, r.stdout[:600])

        # 26 — session-scoped routing
        sp = os.path.join(tmp, "sessp")
        run([PY, ks, "project", "init", sp], cwd=tmp, env=kenv)
        seed_agents(sp, ("x-planner",))
        envf = os.path.join(tmp, "claude_env_file")
        cenv = dict(kenv); cenv["CLAUDE_ENV_FILE"] = envf; cenv["TKSFW_HOST"] = "mac1"
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=sp, env=cenv, inp=json.dumps({"session_id": "C1", "prompt_id": "p1", "source": "startup", "cwd": sp}))
        xenv = dict(kenv); xenv["TKSFW_HOST"] = "mac1"
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=sp, env=xenv, inp=json.dumps({"session_id": "X1", "turn_id": "t1", "source": "startup", "cwd": sp}))
        envtxt = open(envf).read() if os.path.isfile(envf) else ""
        mtok = re.search(r"export TKSFW_SESSION=([0-9A-Za-z]{8})", envtxt)
        check("SessionStart exports TKSFW_SESSION through CLAUDE_ENV_FILE", bool(mtok), envtxt)
        ctok = mtok.group(1) if mtok else ""
        recs = {json.load(open(os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions", f)))["token"]: json.load(open(os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions", f))) for f in os.listdir(os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions"))}
        check("session records carry the host", all(r.get("host") == "mac1" for r in recs.values()), str(recs))
        xtok = next(t for t, r in recs.items() if r["harness"] == "codex")
        r = run([PY, ks, "project", "status"], cwd=sp, env=xenv)
        check("ks project status: sessions table with token/harness/operator/host/routing, no marker when ambiguous",
              "sessions: 2 active" in r.stdout and "token" in r.stdout and "harness" in r.stdout and ctok in r.stdout and xtok in r.stdout and "←" not in r.stdout, r.stdout)
        senv = dict(xenv); senv["TKSFW_SESSION"] = ctok
        r = run([PY, ks, "project", "status"], cwd=sp, env=senv)
        check("ks project status marks the current session from TKSFW_SESSION", f"{ctok}" in r.stdout and "← this session (TKSFW_SESSION)" in r.stdout, r.stdout)
        r = run([PY, ks, "routing", "use", "ibm-openai-cc"], cwd=sp, env=xenv)
        check("project-wide switch refuses while sessions are active and names --session / --force",
              r.returncode != 0 and "2 session(s) active" in r.stderr and "--session [token]" in r.stderr and "--force" in r.stderr, r.stderr)
        r = run([PY, ks, "routing", "use", "ibm-openai-cc", "--session"], cwd=sp, env=xenv)
        check("--session without id and two candidate sessions → error listing the tokens", r.returncode != 0 and "several candidates" in r.stderr and ctok in r.stderr and xtok in r.stderr, r.stderr)
        r = run([PY, ks, "routing", "use", "ibm-openai-cc", "--session"], cwd=sp, env=senv)
        check("--session resolves via TKSFW_SESSION; override written; /model hint; Claude Code caveat",
              r.returncode == 0 and f"session {ctok} (claude) → [routing.ibm-openai-cc] for this session only" in r.stdout and "/model gpt-5.6-sol[1m]" in r.stdout
              and "custom agents keep the project-wide frontmatter model" in r.stdout
              and json.load(open(os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions", ctok + ".json"))).get("routing") == "ibm-openai-cc", r.stdout + r.stderr)
        cfgtxt = open(os.path.join(sp, ".agents", "config.toml")).read()
        check("session override leaves config.toml unpinned", not re.search(r"^selected\s*=", cfgtxt, re.M), cfgtxt[:300])
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=sp, env=cenv,
                inp=json.dumps({"session_id": "C1", "prompt_id": "p2", "hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "Explore", "prompt": "p"}, "cwd": sp}))
        c1 = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=sp, env=xenv,
                inp=json.dumps({"session_id": "X1", "turn_id": "t2", "hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "tool_input": {"agent_type": "x-planner"}, "cwd": sp}))
        x1 = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        check("only the overridden session's spawns use the session table", "gpt-5.6-luna[1m]" in c1 and "[routing.ibm-openai-cc]" in c1 and "[routing.ibm-anthropic]" in x1 and "claude-opus-5" in x1, c1[:150] + " || " + x1[:150])
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=sp, env=cenv | {"TKSFW_ROUTING": "openrouter"},
                inp=json.dumps({"session_id": "C1", "prompt_id": "p2b", "hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "Explore", "prompt": "p"}, "cwd": sp}))
        check("session override beats TKSFW_ROUTING", "[routing.ibm-openai-cc]" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"], r.stdout[:300])
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=sp, env=cenv, inp=json.dumps({"session_id": "C1", "prompt_id": "p3", "cwd": sp, "prompt": "x"}))
        r2 = run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=sp, env=xenv, inp=json.dumps({"session_id": "X1", "turn_id": "t3", "cwd": sp, "prompt": "x"}))
        check("prompt notice: the overridden session is told 'THIS SESSION ONLY'; the other session sees nothing",
              "via session override — THIS SESSION ONLY" in r.stdout and r2.stdout.strip() == "", r.stdout[:300] + " || " + r2.stdout[:100])
        r = run([PY, ks, "routing", "show", "--session", ctok], cwd=sp, env=xenv)
        check("ks routing show --session <token>: override line first, then the table as that harness sees it",
              r.stdout.startswith(f"session {ctok} (claude") and "override → [routing.ibm-openai-cc]" in r.stdout and "harness=claude  routing='ibm-openai-cc'  selected_by=session override" in r.stdout, r.stdout)
        r = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=sp, env=cenv)
        # STATE.md Sessions section lists shards only; write one entry for C1 so the token appears
        open(os.path.join(sp, ".agents", "workarea", f"lessons.{ctok}.yaml"), "w").write(f"- Lssn0001:\n    AuthorAgent: main\n    Model: m\n    Timestamp: \"2026-09-10 09:00:00\"\n    OwnerSessionId: {ctok}\n    OwnerSessionUserName: carlos\n    Title: \"t\"\n    Description: |-\n      x\n    Remarks: |-\n      x\n")
        r = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=sp, env=cenv)
        check("STATE.md Sessions shows the routing override and host", f"routing override [routing.ibm-openai-cc]" in r.stdout and "mac1" in r.stdout, r.stdout[-600:])
        r = run([PY, ks, "routing", "use", "--clear", "--session", ctok], cwd=sp, env=xenv)
        check("--clear --session removes the override", r.returncode == 0 and "override cleared (was [routing.ibm-openai-cc])" in r.stdout
              and "routing" not in json.load(open(os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions", ctok + ".json"))), r.stdout + r.stderr)
        r = run([PY, ks, "routing", "use", "ibm-openai-cc", "--force"], cwd=sp, env=xenv)
        check("--force switches the project for all sessions", r.returncode == 0 and 'selected = "ibm-openai-cc"' in open(os.path.join(sp, ".agents", "config.toml")).read(), r.stdout + r.stderr)
        # one active session on this host by this operator → resolved without env
        os.remove(os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions", xtok + ".json"))
        r = run([PY, ks, "project", "status"], cwd=sp, env=xenv)
        check("single candidate → 'probably yours' marker", "← probably yours (only session on this host by you)" in r.stdout, r.stdout)
        # 3.4.1 — spawning an undefined agent is denied with the fix; a bare role name is called out; built-ins pass
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=sp, env=cenv,
                inp=json.dumps({"session_id": "C1", "prompt_id": "p7", "hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "builder", "prompt": "p"}, "cwd": sp}))
        hs = json.loads(r.stdout)["hookSpecificOutput"]
        check("spawn of a bare role name is denied: 'builder is a ROLE, not an agent', define-agent hint",
              hs["permissionDecision"] == "deny" and "is a ROLE, not an agent" in hs["permissionDecisionReason"] and "define-agent" in hs["permissionDecisionReason"] and "report-builder" in hs["permissionDecisionReason"], r.stdout)
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=sp, env=cenv,
                inp=json.dumps({"session_id": "C1", "prompt_id": "p8", "hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "report-builder", "prompt": "p"}, "cwd": sp}))
        hs = json.loads(r.stdout)["hookSpecificOutput"]
        check("spawn of an undefined <family>-<role> agent is denied naming the missing .toml", hs["permissionDecision"] == "deny" and ".agents/agents/report-builder.toml missing" in hs["permissionDecisionReason"], r.stdout)
        seed_agents(sp, ("report-builder",))
        r = run([PY, os.path.join(plug, "hooks", "route_model.py")], cwd=sp, env=cenv,
                inp=json.dumps({"session_id": "C1", "prompt_id": "p9", "hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "report-builder", "prompt": "p"}, "cwd": sp}))
        hs = json.loads(r.stdout)["hookSpecificOutput"]
        check("once defined, the spawn is allowed and the missing Claude mirror is rendered on the fly",
              hs["permissionDecision"] == "allow" and os.path.isfile(os.path.join(sp, ".claude", "agents", "report-builder.md")), r.stdout[:300])
        r = run([PY, ks, "routing", "resolve", "never-defined-builder"], cwd=sp, env=xenv)
        check("ks routing resolve answers for an undefined name (informational, no existence check)", r.returncode == 0 and '"ok": true' in r.stdout, r.stdout)
        # 27 — 3.5.0: SessionEnd ends a session at once; harness detected for Claude SessionStart; sessions close
        sdir = os.path.join(sp, ".agents", "workarea", ".hook-state", "sessions")      # only C1 survives section 26
        c2env = dict(cenv); c2env["CLAUDE_PROJECT_DIR"] = sp
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=sp, env=c2env, inp=json.dumps({"session_id": "C2", "source": "startup", "cwd": sp}))
        recs = {json.load(open(os.path.join(sdir, f)))["token"]: json.load(open(os.path.join(sdir, f))) for f in os.listdir(sdir) if f.endswith(".json")}
        c2 = next((r for r in recs.values() if r.get("harness_session_id") == "C2"), None)
        check("Claude SessionStart without prompt_id: harness = claude (from CLAUDE_PROJECT_DIR), not unknown", c2 is not None and c2["harness"] == "claude", str(c2))
        with open(os.path.join(sdir, c2["token"] + ".json"), "w") as fh:
            json.dump(c2 | {"harness": "unknown"}, fh)
        run([PY, os.path.join(plug, "hooks", "track_edits.py"), "--phase", "prompt"], cwd=sp, env=cenv,
            inp=json.dumps({"session_id": "C2", "prompt_id": "q1", "hook_event_name": "UserPromptSubmit", "prompt": "hi", "cwd": sp}))
        c2b = json.load(open(os.path.join(sdir, c2["token"] + ".json")))
        check("an 'unknown' harness is backfilled by the next heartbeat that can tell", c2b["harness"] == "claude", str(c2b))
        r = run([PY, ks, "project", "status"], cwd=sp, env=xenv)
        check("status: 2 active before SessionEnd, wording explains 'active'", "sessions: 2 active (ended by the harness, or heartbeat within the last 30 min)" in r.stdout, r.stdout[:400])
        r = run([PY, os.path.join(plug, "hooks", "session_end.py")], cwd=sp, env=cenv,
                inp=json.dumps({"session_id": "C2", "hook_event_name": "SessionEnd", "reason": "prompt_input_exit", "cwd": sp}))
        c2c = json.load(open(os.path.join(sdir, c2["token"] + ".json")))
        check("SessionEnd hook marks the record ended with the reason, exit 0", r.returncode == 0 and c2c.get("ended") and c2c.get("end_reason") == "prompt_input_exit", r.stdout + r.stderr + str(c2c))
        r = run([PY, ks, "project", "status"], cwd=sp, env=xenv)
        check("status: the ended session no longer counts as active; ended count shown; its row gone",
              "sessions: 1 active" in r.stdout and "1 ended in the last 3 h" in r.stdout and c2["token"] not in r.stdout, r.stdout[:500])
        r = run([PY, ks, "routing", "use", "ibm-openai-cc", "--session", ctok], cwd=sp, env=xenv)
        r = run([PY, ks, "routing", "use", "ibm-anthropic-cc"], cwd=sp, env=xenv)
        check("project-wide switch is still guarded by the remaining active session only", r.returncode != 0 and ctok in r.stderr and c2["token"] not in r.stderr, r.stderr)
        run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=sp, env=c2env, inp=json.dumps({"session_id": "C2", "source": "resume", "cwd": sp}))
        c2d = json.load(open(os.path.join(sdir, c2["token"] + ".json")))
        check("a resumed session after SessionEnd is active again", not c2d.get("ended"), str(c2d))
        r = run([PY, ks, "project", "sessions", "close", "nope1234"], cwd=sp, env=xenv)
        check("ks project sessions close: unknown token → error", r.returncode != 0 and "not found" in r.stderr, r.stderr)
        r = run([PY, ks, "project", "sessions", "close", ctok], cwd=sp, env=xenv)
        r2 = run([PY, ks, "project", "status"], cwd=sp, env=xenv)
        check("ks project sessions close <token> ends it; status drops to 1 active", r.returncode == 0 and ctok in r.stdout and "sessions: 1 active" in r2.stdout, r.stdout + r2.stdout[:300])
        r = run([PY, ks, "project", "sessions", "close", "--stale"], cwd=sp, env=xenv)
        check("sessions close --stale closes nothing while heartbeats are fresh", r.returncode == 0 and "closed 0" in r.stdout, r.stdout)
        old = json.load(open(os.path.join(sdir, c2["token"] + ".json"))); old["last_seen"] = time.time() - 4000
        json.dump(old, open(os.path.join(sdir, c2["token"] + ".json"), "w"))
        r = run([PY, ks, "project", "sessions", "close", "--stale"], cwd=sp, env=xenv)
        r2 = run([PY, ks, "project", "update"], cwd=sp, env=xenv)
        check("sessions close --stale ends the old record; project update then runs without --force", "closed 1" in r.stdout and c2["token"] in r.stdout and r2.returncode == 0, r.stdout + r2.stderr[:300])
        r = run([PY, ks, "project", "sessions"], cwd=sp, env=xenv)
        check("ks project sessions (list) prints the table with the ended count", "sessions: 0 active" in r.stdout and "2 ended in the last 3 h" in r.stdout, r.stdout)
        r = run([PY, ks, "doctor"], cwd=sp, env=xenv)
        check("doctor: version line ok when project == installed", re.search(r"ok\s+version project", r.stdout) is not None, r.stdout[-600:])

        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()   # the kernel itself, not the project copy (a test appends to that)
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

        # 23 — Project layers L3/L4 (2.2.0)
        lp = os.path.join(tmp, "layersp")
        run([PY, ks, "project", "init", lp], cwd=tmp, env=kenv)
        L_HOOK = os.path.join(plug, "hooks", "layers.py")
        def lstart(sid, src="startup"):
            r = run([PY, os.path.join(plug, "hooks", "inject_state.py")], cwd=lp, env=kenv,
                    inp=json.dumps({"session_id": sid, "turn_id": "l1", "source": src, "cwd": lp}))
            try:
                return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
            except Exception:
                return ""
        def lblock(text):
            return text.split("<!-- tksfw:layers -->")[1].split("<!-- /tksfw:layers -->")[0] if "<!-- tksfw:layers -->" in text else ""
        r = run([PY, L_HOOK, "resolve", "--json"], cwd=lp, env=kenv)
        check("layers: nothing resolves on a bare project → exit 3, empty list", r.returncode == 3 and json.loads(r.stdout)["layers"] == [] and json.loads(r.stdout)["tier"] == "none", r.stdout[:200] + r.stderr[:200])
        t0 = lstart("L0")
        check("SessionStart on a fresh project without layers injects nothing (unchanged behaviour)", t0 == "" or "tksfw:layers" not in t0, t0[:200])
        open(os.path.join(lp, "KS_PROJECT.md"), "w").write("---\nks_layer: project\ntitle: Engagement archetype\n---\n# Archetype\nrun it like this\n")
        open(os.path.join(lp, "KS_SPEC.md"), "w").write("# ACME landing zone review\n\nspec\n")
        r = run([PY, L_HOOK, "resolve", "--json"], cwd=lp, env=kenv)
        d = json.loads(r.stdout)
        check("layers: convention resolves L3 + L4 with titles (frontmatter / first heading) and status new",
              r.returncode == 0 and d["tier"] == "convention" and [e["layer"] for e in d["layers"]] == ["l3", "l4"]
              and d["layers"][0]["title"] == "Engagement archetype" and d["layers"][1]["title"] == "ACME landing zone review"
              and all(e["journal_status"] == "new" and e["source"] == "convention" and len(e["hash"]) == 64 for e in d["layers"]) and d["warnings"] == [], r.stdout[:600])
        t1 = lstart("L1")
        b1 = lblock(t1)
        check("SessionStart injects the layers block on a fresh project (no STATE yet), marked, with both rows as new",
              "| L3 | `KS_PROJECT.md` | new, not yet journaled |" in b1 and "| L4 | `KS_SPEC.md` | new, not yet journaled |" in b1
              and "Read L3 then L4 in full" in b1 and "ks-start" in b1, t1[:800])
        check("layers block stays within its 600-byte cap", 0 < len(b1.encode()) <= 600, str(len(b1.encode())))
        t2 = lstart("L2")
        check("second start: statuses unchanged (hashes journaled by the hook)", "| L3 | `KS_PROJECT.md` | unchanged |" in lblock(t2) and "| L4 | `KS_SPEC.md` | unchanged |" in lblock(t2), lblock(t2))
        check("state section is marked when present", ("<!-- tksfw:state -->" in t2) == ("Session token:" in t2), t2[:300])
        with open(os.path.join(lp, "KS_SPEC.md"), "a") as fh:
            fh.write("\nmore scope\n")
        t3 = lstart("L3", "compact")
        check("after an edit the compaction re-injection reports L4 changed with the re-read hint", "| L4 | `KS_SPEC.md` | changed since last session |" in lblock(t3) and "Re-read changed layers" in lblock(t3) and "| L3 | `KS_PROJECT.md` | unchanged |" in lblock(t3), lblock(t3))
        t4 = lstart("L4")
        check("…and the next start is unchanged again (block re-journaled)", "| L4 | `KS_SPEC.md` | unchanged |" in lblock(t4), lblock(t4))
        # watched + classified + reported
        run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=lp, env=kenv, inp=json.dumps({"session_id": "L4", "turn_id": "l2", "hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": lp, "tool_input": {"file_path": os.path.join(lp, "KS_SPEC.md")}}))
        with open(os.path.join(lp, "KS_SPEC.md"), "a") as fh:
            fh.write("agent edit\n")
        r = run([PY, os.path.join(plug, "hooks", "track_edits.py")], cwd=lp, env=kenv, inp=json.dumps({"session_id": "L4", "turn_id": "l2", "hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": lp, "tool_input": {"file_path": os.path.join(lp, "KS_SPEC.md")}}))
        jl = [json.loads(l) for l in open(os.path.join(host_state(lp), "journal.jsonl")) if l.strip()]
        cls = [c for e in jl for c in e.get("changed", []) if c["path"] == "KS_SPEC.md"]
        check("PostToolUse journals the L4 edit as class layer:l4, attributed own", cls and cls[-1]["class"] == "layer:l4" and cls[-1]["attrib"] == "own", str(cls[-1:]))
        r = run([PY, os.path.join(plug, "hooks", "check_ledgers_on_stop.py")], cwd=lp, env=kenv, inp=json.dumps({"session_id": "L4", "turn_id": "l2", "cwd": lp}))
        check("Stop hook reminds about the un-logged layer edit with the ARCHETYPE/PROJECT hint", "Project layer edits without a later `changes.yaml` entry" in r.stdout and "KS_SPEC.md" in r.stdout and "PROJECT for L4" in r.stdout, r.stdout[:400])
        r = run([PY, os.path.join(plug, "hooks", "refresh_state.py"), "--print"], cwd=lp, env=kenv)
        check("STATE.md lists the layer edit under un-logged edits", "layer: KS_SPEC.md" in r.stdout, r.stdout[-600:])
        # config tier: pin, missing, L4 alone, clear; ks verbs; update keeps the stanza
        r = run([PY, ks, "layers", "pin", "--l4", "docs/brief.md"], cwd=lp, env=kenv)
        man = json.load(open(os.path.join(lp, ".agents", ".tksfw.json")))
        check("ks layers pin writes the manifest stanza and prints the effect line", r.returncode == 0 and man.get("layers") == {"l4": "docs/brief.md"} and "Layer: METHOD" in r.stdout, r.stdout + r.stderr)
        r = run([PY, ks, "layers", "resolve", "--json"], cwd=lp, env=kenv)
        d = json.loads(r.stdout)
        check("declared but missing L4 → exit 4, status missing, source config; L3 still by convention",
              r.returncode == 4 and d["layers"][1] == d["layers"][1] | {"path": "docs/brief.md", "source": "config", "exists": False, "journal_status": "missing"} and d["layers"][0]["source"] == "convention", r.stdout[:500])
        b = run([PY, L_HOOK, "section"], cwd=lp, env=kenv).stdout
        check("section names the missing declaration and how to fix it", "declared in .agents/.tksfw.json but missing" in b and "ks layers pin" in b, b)
        os.makedirs(os.path.join(lp, "docs"), exist_ok=True)
        open(os.path.join(lp, "docs", "brief.md"), "w").write("# Brief\n")
        r = run([PY, ks, "layers", "resolve"], cwd=lp, env=kenv)
        check("declared L4 found → exit 0, tier config in the human view", r.returncode == 0 and "docs/brief.md  [config]" in r.stdout, r.stdout)
        r = run([PY, ks, "layers", "resolve", "--l4", "KS_SPEC.md", "--json"], cwd=lp, env=kenv)
        check("arguments (tier 1) win over the config for the key they name", json.loads(r.stdout)["layers"][1]["path"] == "KS_SPEC.md" and json.loads(r.stdout)["layers"][1]["source"] == "args" and json.loads(r.stdout)["tier"] == "args", r.stdout[:400])
        r = run([PY, ks, "layers", "pin", "--l3", "../outside.md"], cwd=lp, env=kenv)
        check("pin refuses a path outside the project", r.returncode != 0 and "project-relative" in r.stderr, r.stderr)
        r = run([PY, os.path.join(plug, "skills", "tksfw-init", "assets", "new_project.py"), lp, "--update", "--no-sync"], cwd=tmp, env=kenv)
        man = json.load(open(os.path.join(lp, ".agents", ".tksfw.json")))
        check("new_project --update preserves the layers stanza", r.returncode == 0 and man.get("layers") == {"l4": "docs/brief.md"}, r.stdout[-300:] + str(man.get("layers")))
        r = run([PY, ks, "project", "status"], cwd=lp, env=kenv)
        check("ks project status prints the layers line", "layers  : L3 KS_PROJECT.md" in r.stdout and "L4 docs/brief.md" in r.stdout, r.stdout)
        r = run([PY, ks, "layers", "pin", "--clear"], cwd=lp, env=kenv)
        os.remove(os.path.join(lp, "KS_PROJECT.md"))
        r = run([PY, ks, "layers", "resolve", "--json"], cwd=lp, env=kenv)
        d = json.loads(r.stdout)
        check("after --clear and without L3: L4 alone by convention is valid (exit 0, one row)", r.returncode == 0 and "layers" not in json.load(open(os.path.join(lp, ".agents", ".tksfw.json"))) and [e["layer"] for e in d["layers"]] == ["l4"], r.stdout[:300])
        check("section for L4 alone says Read L4", "Read L4 in full" in run([PY, L_HOOK, "section"], cwd=lp, env=kenv).stdout)
        open(os.path.join(lp, "KS_PROJECT.md"), "w").write("---\nks_layer: spec\n---\n# Wrong marker\n")
        r = run([PY, ks, "layers", "resolve", "--json"], cwd=lp, env=kenv)
        check("frontmatter ks_layer mismatch is a warning, not a failure", r.returncode == 0 and any("ks_layer='spec'" in w and "L3" in w for w in json.loads(r.stdout)["warnings"]), r.stdout[-300:])
        r = run([PY, ks, "layers", "journal"], cwd=lp, env=kenv)
        check("ks layers journal records the hashes", r.returncode == 0 and "layers journaled: KS_PROJECT.md, KS_SPEC.md" in r.stdout and os.path.isfile(os.path.join(host_state(lp), "layers.json")), r.stdout + r.stderr)
        # skill, prompts, kernel
        check("ks-start skill bundled in the plugin and present in the template", os.path.isfile(os.path.join(plug, "skills", "ks-start", "SKILL.md")) and os.path.isfile(os.path.join(REPO, "template", ".agents", "skills", "ks-start", "SKILL.md")))
        sk = open(os.path.join(plug, "skills", "ks-start", "SKILL.md"), encoding="utf-8").read()
        check("ks-start skill calls the resolver and journals, never restates the tiers as policy", "ks layers resolve --json" in sk and "ks layers journal" in sk and "Layer conflict:" in sk and sk.startswith("---\nname: ks-start"))
        check("ks-start mirrored into .claude/skills of the full-mode project", os.path.islink(os.path.join(full, ".claude", "skills", "ks-start")) or os.path.isdir(os.path.join(full, ".claude", "skills", "ks-start")))
        check("no project-level Codex prompts in the template (Codex reads only ~/.codex/prompts; deprecated)", not os.path.isdir(os.path.join(REPO, "template", ".codex", "prompts")))
        rl = open(os.path.join(plug, "skills", "ks-reload", "SKILL.md"), encoding="utf-8").read()
        check("ks-reload skill replaces the reload prompt: names the layers, re-reads from disk, journals", rl.startswith("---\nname: ks-reload") and "KS_PROJECT.md" in rl and "KS_SPEC.md" in rl and "ks layers journal" in rl)
        # project update prunes retired, pristine template files (2.7.0)
        stale = os.path.join(lp, ".codex", "prompts")
        os.makedirs(stale, exist_ok=True)
        open(os.path.join(stale, "ks-start.md"), "w").write("old prompt\n")
        open(os.path.join(stale, "edited.md"), "w").write("edited by the operator\n")
        import hashlib as _hl
        mfp = os.path.join(lp, ".agents", ".tksfw.json")
        mf = json.load(open(mfp))
        mf["files"][".codex/prompts/ks-start.md"] = _hl.sha256(b"old prompt\n").hexdigest()
        mf["files"][".codex/prompts/edited.md"] = "0" * 64
        json.dump(mf, open(mfp, "w"), indent=2, sort_keys=True)
        r = run([PY, ks, "project", "update", lp, "--force"], cwd=tmp, env=kenv)
        check("ks project update removes retired pristine files and keeps edited ones (listed)",
              not os.path.exists(os.path.join(stale, "ks-start.md")) and os.path.exists(os.path.join(stale, "edited.md"))
              and "removed (retired by the template, pristine): 1" in r.stdout and "retired but edited locally" in r.stdout, r.stdout[-500:])
        agents_md = open(os.path.join(REPO, "template", "AGENTS.md"), encoding="utf-8").read()
        check("AGENTS.md: Project Layers section, precedence rule, no legacy layer file names, kernel < 19,000 B",
              "#### Project Layers (L3 / L4)" in agents_md and "L4 overrides L3" in agents_md and "neither overrides this file or the method" in agents_md
              and "`KS_PROJECT.md` (L3) + `KS_SPEC.md` (L4)" in agents_md and "_project-archetype.md" not in agents_md and "_project.md" not in agents_md
              and len(agents_md.encode()) < 19000, str(len(agents_md.encode())))

    # 6 — committed plugin copy is current
    r = run([PY, os.path.join(REPO, "tools", "build_plugin.py"), "--check"])
    check("plugins/* committed copies are up to date", r.returncode == 0, r.stdout)

    print(f"\n{'ALL PASSED' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
