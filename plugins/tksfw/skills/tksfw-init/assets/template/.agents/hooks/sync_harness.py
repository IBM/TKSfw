#!/usr/bin/env python3
"""Keep the two harness layers (Codex CLI, Claude Code) in sync with the neutral `.agents/` source.

  .agents/hooks/hooks.json   ──►  .codex/hooks.json            verbatim (same format)
                             ──►  .claude/settings.json        `hooks` key replaced; other settings kept
  .agents/skills/<name>/     ──►  .claude/skills/<name>        per-skill mirror: a relative
                                                                symlink (`../../.agents/skills/<name>`)
                                                                or a managed copy (see --mode)
  .agents/agents/<name>.toml ──►  .codex/agents/<name>.toml    Codex mirror (model lines rendered
                                                                from the tier in .agents/models.toml)
                             ──►  .claude/agents/<name>.md     Claude Code mirror (frontmatter: name,
                                                                description, model, effort, tools).
                                                                Both are managed by agentlib.py; the
                                                                PostToolUse hook renders them on every
                                                                validated write, --models re-renders all
                                                                (after editing models.toml)

Why per-skill entries and not one link for the whole directory: Claude Code documents that a
`<skill-name>` entry may be a symlink, while a symlinked `.claude/skills` directory is not
documented, Claude Code writes its own files into that directory, and the folder name `synced`
is reserved there. Codex reads `.agents/skills` natively, so nothing is generated for it.

Why a copy mode: Box Drive lists symbolic links among the file types it ignores, so links made
inside a Box-synced project do not reach the cloud or other machines. `--mode auto` (default)
picks `copy` when the project lives under a cloud-storage mount (macOS `~/Library/CloudStorage/`
or a path containing `/Box`) and `link` otherwise. A managed copy carries a `.mirror.json`
marker (source + content hash) so the script can refresh, verify and remove it; a directory
WITHOUT that marker is treated as hand-made and never touched.

Usage:
    python3 .agents/hooks/sync_harness.py                 # apply (idempotent)
    python3 .agents/hooks/sync_harness.py --check         # report drift, exit 1 if anything is stale
    python3 .agents/hooks/sync_harness.py --hooks         # only the hook mirrors
    python3 .agents/hooks/sync_harness.py --skills        # only the skill mirrors
    python3 .agents/hooks/sync_harness.py --models        # only the agent model rendering
    python3 .agents/hooks/sync_harness.py --routing ibm   # force a [routing.<key>] table
    python3 .agents/hooks/sync_harness.py --mode copy     # force copy | link | auto

Rules for skill mirrors:
  * a source skill is a directory under .agents/skills/ that contains SKILL.md
  * link mode: a correct link is left alone; a wrong/dangling link is replaced
  * copy mode: a managed copy is refreshed when the source content hash differs
  * a REAL directory/file at .claude/skills/<name> without the marker is never touched (conflict)
  * stale mirrors (link or managed copy) whose source skill disappeared are removed
  * the reserved name `synced` is skipped
This script never writes CLAUDE.md / CLAUDE.local.md — instruction files are yours.
Remember: Codex trusts hooks by hash — after hooks.json changes, re-trust in `/hooks`.
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import shutil
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
os.environ.setdefault("TKSFW_PROJECT_ROOT", ROOT)          # hooklib must agree on the root
sys.path.insert(0, HERE)
import route_model as RM  # noqa: E402
HOOKS_SRC = os.path.join(HERE, "hooks.json")
CODEX_HOOKS = os.path.join(ROOT, ".codex", "hooks.json")
CLAUDE_SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
SKILLS_SRC = os.path.join(ROOT, ".agents", "skills")
SKILLS_DST = os.path.join(ROOT, ".claude", "skills")
RESERVED = {"synced"}
MARKER = ".mirror.json"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".DS_Store", MARKER)


def rel(p):
    return os.path.relpath(p, ROOT)


def dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


# ----------------------------------------------------------------------------- hooks
def sync_hooks(check):
    """Return list of (status, path) where status is 'ok' | 'stale' | 'wrote'."""
    with open(HOOKS_SRC, encoding="utf-8") as fh:
        src = json.load(fh)
    hooks = src["hooks"]
    codex_out = dump({"description": src.get("description", ""), "hooks": hooks})
    settings = {}
    if os.path.exists(CLAUDE_SETTINGS):
        try:
            with open(CLAUDE_SETTINGS, encoding="utf-8") as fh:
                settings = json.load(fh)
        except Exception:
            settings = {}
    settings["hooks"] = hooks
    claude_out = dump(settings)

    results = []
    for path, out in ((CODEX_HOOKS, codex_out), (CLAUDE_SETTINGS, claude_out)):
        cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if cur == out:
            results.append(("ok", rel(path)))
        elif check:
            results.append(("stale", rel(path)))
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out)
            results.append(("wrote", rel(path)))
    return results


# ----------------------------------------------------------------------------- skills
def source_skills():
    names = []
    if not os.path.isdir(SKILLS_SRC):
        return names
    for name in sorted(os.listdir(SKILLS_SRC)):
        d = os.path.join(SKILLS_SRC, name)
        if name.startswith(".") or name in RESERVED or not os.path.isdir(d):
            continue
        if os.path.isfile(os.path.join(d, "SKILL.md")):
            names.append(name)
    return names


def expected_target(name):
    # relative so the project stays relocatable (Box, clones, other machines)
    return os.path.join("..", "..", ".agents", "skills", name)


def tree_hash(root):
    """Content hash of a skill directory (paths + bytes), ignoring caches and the marker."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for f in sorted(filenames):
            if f in (".DS_Store", MARKER):
                continue
            p = os.path.join(dirpath, f)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def auto_mode():
    r = ROOT.replace("\\", "/")
    return "copy" if ("/Library/CloudStorage/" in r or "/Box" in r) else "link"


def read_marker(path):
    try:
        with open(os.path.join(path, MARKER), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def make_copy(src, dst, name):
    if os.path.islink(dst):
        os.remove(dst)
    elif os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=COPY_IGNORE)
    with open(os.path.join(dst, MARKER), "w", encoding="utf-8") as fh:
        json.dump({"source": f".agents/skills/{name}", "sha256": tree_hash(src),
                   "managed_by": ".agents/hooks/sync_harness.py"}, fh, indent=2)
        fh.write("\n")


def sync_skills(check, mode):
    """Return list of (status, path[, detail]) with status in
    ok | stale | linked | relinked | copied | refreshed | removed | conflict | skipped."""
    results = []
    names = source_skills()
    if not names:
        return [("skipped", rel(SKILLS_SRC), "no skills with SKILL.md")]
    if os.path.islink(SKILLS_DST):
        return [("conflict", rel(SKILLS_DST),
                 "is itself a symlink; make it a real directory (see docstring)")]
    if not check:
        os.makedirs(SKILLS_DST, exist_ok=True)

    for name in names:
        src = os.path.join(SKILLS_SRC, name)
        dst = os.path.join(SKILLS_DST, name)
        want = expected_target(name)
        is_link = os.path.islink(dst)
        marker = None if is_link or not os.path.isdir(dst) else read_marker(dst)

        if mode == "link":
            if is_link:
                have = os.readlink(dst)
                if (os.path.normpath(have) == os.path.normpath(want)
                        and os.path.isfile(os.path.join(dst, "SKILL.md"))):
                    results.append(("ok", rel(dst)))
                    continue
                if check:
                    results.append(("stale", rel(dst), f"points to {have}"))
                    continue
                os.remove(dst)
                os.symlink(want, dst, target_is_directory=True)
                results.append(("relinked", rel(dst)))
            elif marker is not None:                       # managed copy -> convert to link
                if check:
                    results.append(("stale", rel(dst), "managed copy, link expected"))
                    continue
                shutil.rmtree(dst)
                os.symlink(want, dst, target_is_directory=True)
                results.append(("relinked", rel(dst)))
            elif os.path.exists(dst):
                results.append(("conflict", rel(dst), "hand-made directory/file, not touched"))
            elif check:
                results.append(("stale", rel(dst), "missing"))
            else:
                os.symlink(want, dst, target_is_directory=True)
                results.append(("linked", rel(dst)))
        else:  # copy
            if marker is not None:
                if marker.get("sha256") == tree_hash(src) and tree_hash(dst) == marker.get("sha256"):
                    results.append(("ok", rel(dst)))
                    continue
                if check:
                    results.append(("stale", rel(dst), "content differs from source"))
                    continue
                make_copy(src, dst, name)
                results.append(("refreshed", rel(dst)))
            elif is_link:                                  # link -> convert to managed copy
                if check:
                    results.append(("stale", rel(dst), "symlink, copy expected"))
                    continue
                make_copy(src, dst, name)
                results.append(("copied", rel(dst)))
            elif os.path.exists(dst):
                results.append(("conflict", rel(dst), "hand-made directory/file, not touched"))
            elif check:
                results.append(("stale", rel(dst), "missing"))
            else:
                make_copy(src, dst, name)
                results.append(("copied", rel(dst)))

    # mirrors whose source skill was removed/renamed
    if os.path.isdir(SKILLS_DST):
        for entry in sorted(os.listdir(SKILLS_DST)):
            if entry in names or entry.startswith("."):
                continue
            p = os.path.join(SKILLS_DST, entry)
            managed = False
            if os.path.islink(p):
                managed = ".agents/skills/" in os.readlink(p).replace("\\", "/") and not os.path.exists(p)
            elif os.path.isdir(p):
                m = read_marker(p)
                managed = bool(m) and not os.path.isdir(os.path.join(SKILLS_SRC, entry))
            if not managed:
                continue
            if check:
                results.append(("stale", rel(p), "orphan mirror"))
            else:
                if os.path.islink(p):
                    os.remove(p)
                else:
                    shutil.rmtree(p)
                results.append(("removed", rel(p)))
    return results


# ----------------------------------------------------------------------------- models
def sync_models(check):
    """Agent definitions: .agents/agents/*.toml → .codex/agents/*.toml + .claude/agents/*.md
    (see agentlib.py). Bulk path; track_edits.py renders incrementally on every validated write."""
    import agentlib
    return agentlib.sync(check=check)


# ----------------------------------------------------------------------------- main
def main():
    args = set(sys.argv[1:])
    check = "--check" in args
    mode = "auto"
    argv = sys.argv[1:]
    if "--mode" in argv and argv.index("--mode") + 1 < len(argv):
        mode = argv[argv.index("--mode") + 1]
    if mode not in ("auto", "link", "copy"):
        print("--mode must be auto | link | copy"); sys.exit(2)
    if mode == "auto":
        mode = auto_mode()
    if "--routing" in argv and argv.index("--routing") + 1 < len(argv):
        os.environ["TKSFW_ROUTING"] = argv[argv.index("--routing") + 1]
    scoped = {"--hooks", "--skills", "--models"} & args
    do_hooks = not scoped or "--hooks" in args
    do_skills = not scoped or "--skills" in args
    do_models = not scoped or "--models" in args

    results = []
    if do_hooks:
        results += [("hooks",) + r for r in sync_hooks(check)]
    if do_skills:
        results += [("skills",) + r for r in sync_skills(check, mode)]
    if do_models:
        results += [("models",) + r for r in sync_models(check)]

    bad = 0
    for r in results:
        section, status, path = r[0], r[1], r[2]
        detail = f"  ({r[3]})" if len(r) > 3 else ""
        if status in ("stale", "conflict"):
            bad += 1
        if status == "ok" and "--verbose" not in args:
            continue
        if status == "info":
            print(f"{section:6} {path}")
            continue
        print(f"{section:6} {status:9} {path}{detail}")
    n_ok = sum(1 for r in results if r[1] == "ok")
    if do_skills:
        print(f"skills mirror mode: {mode}")
    if check:
        print("ok" if not bad else f"{bad} item(s) need attention — run sync_harness.py")
        sys.exit(1 if bad else 0)
    print(f"done: {n_ok} already in sync, "
          f"{sum(1 for r in results if r[1] in ('wrote', 'linked', 'relinked', 'copied', 'refreshed', 'removed'))} changed, "
          f"{sum(1 for r in results if r[1] == 'conflict')} conflict(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
