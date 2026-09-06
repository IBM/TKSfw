#!/usr/bin/env python3
"""Instantiate the TKS method in a project folder from template/ (works on Box-synced folders).

    python3 tools/new_project.py /path/to/project                 # full: method text + in-project tooling
    python3 tools/new_project.py /path/to/project --plugin-mode   # method text only; tooling comes from
                                                                  # the installed tksfw plugin
    python3 tools/new_project.py /path/to/project --update        # refresh unmodified framework files,
                                                                  # report locally edited ones, never overwrite them
    python3 tools/new_project.py /path/to/project --disable       # disarm: hooks/routing become inert here
    python3 tools/new_project.py /path/to/project --enable        # re-arm
    python3 tools/new_project.py --set-operator "Carlos Veira"    # write ~/.config/tksfw/user.toml (per user, once)
    python3 tools/new_project.py --show-operator                  # resolved operator name and its source

Full mode copies:   AGENTS.md, CLAUDE.local.md, .agents/{hooks,skills,workarea}, .codex/
                    then runs .agents/hooks/sync_harness.py (generates .codex/hooks.json,
                    .claude/settings.json and the .claude/skills mirrors).
Plugin mode copies: AGENTS.md, CLAUDE.local.md, .agents/workarea/, .codex/config.toml, .codex/prompts/
                    (no hooks, no skills, no harness mirrors — the plugin provides them).

A manifest `.agents/.tksfw.json` records the framework version, `enabled` (the ARMING switch every
hook checks first — false makes the framework inert in this project on both harnesses) and the
SHA-256 of every file installed, so --update can tell "unchanged since install" (safe to refresh)
from "edited locally" (kept, listed for manual merge). Standard library only; no git required.
"""
import sys
sys.dont_write_bytecode = True
import os
import json
import shutil
import hashlib
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
# Two layouts: repository (tools/new_project.py + ../template + ../VERSION) and plugin skill assets
# (skills/tksfw-init/assets/{new_project.py,template/,VERSION}).
REPO = HERE if os.path.isdir(os.path.join(HERE, "template")) else os.path.normpath(os.path.join(HERE, ".."))
TEMPLATE = os.path.join(REPO, "template")
MANIFEST_REL = os.path.join(".agents", ".tksfw.json")
SKIP_NAMES = {"__pycache__", ".DS_Store", ".hook-state", "STATE.md", ".mirror.json"}
PLUGIN_MODE_EXCLUDE_TOP = {os.path.join(".agents", "hooks"), os.path.join(".agents", "skills")}


def version():
    with open(os.path.join(REPO, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def template_files(plugin_mode):
    for dirpath, dirnames, filenames in os.walk(TEMPLATE):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
        rel_dir = os.path.relpath(dirpath, TEMPLATE)
        rel_dir = "" if rel_dir == "." else rel_dir
        if plugin_mode and any(rel_dir == x or rel_dir.startswith(x + os.sep) for x in PLUGIN_MODE_EXCLUDE_TOP):
            continue
        for f in sorted(filenames):
            if f in SKIP_NAMES or f.startswith("._") or f.endswith(".pyc"):
                continue
            yield os.path.join(rel_dir, f) if rel_dir else f


def load_manifest(target):
    p = os.path.join(target, MANIFEST_REL)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?")
    ap.add_argument("--plugin-mode", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="skip sync_harness.py after copying")
    ap.add_argument("--disable", action="store_true", help="set enabled=false in .agents/.tksfw.json (disarm)")
    ap.add_argument("--enable", action="store_true", help="set enabled=true in .agents/.tksfw.json (re-arm)")
    ap.add_argument("--set-operator", metavar="NAME", help="write the per-user config ~/.config/tksfw/user.toml (OwnerSessionUserName)")
    ap.add_argument("--show-operator", action="store_true", help="print the resolved operator name and its source; exit 1 when unset")
    a = ap.parse_args()
    if a.set_operator is not None or a.show_operator:
        sys.path.insert(0, os.path.join(TEMPLATE, ".agents", "hooks"))
        os.environ.setdefault("TKSFW_PROJECT_ROOT", os.getcwd())
        import hooklib as H
        if a.set_operator is not None:
            path = H.write_operator(a.set_operator)
            print(f"operator set: {a.set_operator.strip()!r} → {path}")
        name, src = H.operator_source()
        if not name:
            sys.exit(f"operator UNKNOWN — run --set-operator \"<name>\" (writes {H.USER_CONFIG}) or export TKSFW_USER")
        print(f"operator: {name}  (source: {src}{'' if src != 'git' else ' — fallback; set it with --set-operator'})")
        return
    if not a.target:
        ap.error("target is required")
    target = os.path.abspath(a.target)
    os.makedirs(target, exist_ok=True)
    prev = load_manifest(target)
    if a.disable or a.enable:
        if prev is None:
            sys.exit(f"{target} has no .agents/.tksfw.json — initialise it first (or --update an existing project)")
        prev["enabled"] = bool(a.enable) and not a.disable
        with open(os.path.join(target, MANIFEST_REL), "w", encoding="utf-8") as fh:
            json.dump(prev, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"TKSfw {'ARMED' if prev['enabled'] else 'DISARMED'} in {target} (.agents/.tksfw.json enabled={str(prev['enabled']).lower()})")
        return
    if prev and not a.update:
        sys.exit(f"{target} already carries TKSfw v{prev.get('version')} — use --update to refresh it")
    if a.update and prev:
        plugin_mode = prev.get("plugin_mode", False) if not a.plugin_mode else True
    else:
        plugin_mode = a.plugin_mode
    prev_hashes = (prev or {}).get("files", {})

    installed, refreshed, kept, unchanged = [], [], [], []
    new_hashes = {}
    for rel in template_files(plugin_mode):
        src = os.path.join(TEMPLATE, rel)
        dst = os.path.join(target, rel)
        h = sha256(src)
        new_hashes[rel] = h
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            installed.append(rel)
            continue
        cur = sha256(dst)
        if cur == h:
            unchanged.append(rel)
        elif rel in prev_hashes and prev_hashes[rel] == cur:
            shutil.copy2(src, dst)                     # untouched since install: safe to refresh
            refreshed.append(rel)
        else:
            kept.append(rel)                           # locally edited (or pre-existing): never overwrite

    manifest = {"framework": "TKSfw", "version": version(), "plugin_mode": plugin_mode,
                "enabled": (prev or {}).get("enabled", True) is not False, "files": new_hashes}
    mp = os.path.join(target, MANIFEST_REL)
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"TKSfw v{manifest['version']} → {target}  ({'plugin' if plugin_mode else 'full'} mode)")
    for label, items in (("installed", installed), ("refreshed", refreshed), ("kept (edited locally)", kept)):
        if items:
            print(f"  {label}: {len(items)}")
            for r in items[:40]:
                print(f"    {r}")
    print(f"  unchanged: {len(unchanged)}")

    if not plugin_mode and not a.no_sync:
        sync = os.path.join(target, ".agents", "hooks", "sync_harness.py")
        if os.path.isfile(sync):
            print("running sync_harness.py …")
            subprocess.run([sys.executable, sync], cwd=target, check=False)
    print("\nNext: launch Codex in the project once to trust the .codex layer and, if hooks changed, "
          "re-trust them in /hooks. Record the install/update in .agents/workarea/changes.yaml (Layer: METHOD).")
    if kept:
        print(f"Review the {len(kept)} locally edited file(s) against template/ and merge by hand.")


if __name__ == "__main__":
    main()
