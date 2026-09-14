#!/usr/bin/env python3
"""Instantiate the TKS method in a project folder from template/ (works on Box-synced folders).

    python3 tools/new_project.py /path/to/project                 # full: method text + in-project tooling
    python3 tools/new_project.py /path/to/project --plugin-mode   # method text only; tooling comes from
                                                                  # the installed tksfw plugin
    python3 tools/new_project.py /path/to/project --update        # refresh unmodified framework files,
                                                                  # report locally edited ones, never overwrite them
    python3 tools/new_project.py /path/to/project --drift         # report only: unchanged / outdated / edited / missing
    python3 tools/new_project.py /path/to/project --disable       # disarm: hooks/routing become inert here
    python3 tools/new_project.py /path/to/project --enable        # re-arm
    python3 tools/new_project.py --set-operator "Carlos Veira"    # write ~/.config/tksfw/user.toml (per user, once)
    python3 tools/new_project.py --show-operator                  # resolved operator name and its source

Full mode copies:   AGENTS.md, CLAUDE.local.md, .agents/{hooks,skills,workarea}, .codex/, .claude/settings.json
                    then runs .agents/hooks/sync_harness.py (generates .codex/hooks.json,
                    .claude/settings.json and the .claude/skills mirrors).
Plugin mode copies: AGENTS.md, CLAUDE.local.md, .agents/workarea/, .codex/config.toml,
                    .claude/settings.json (permission deny rules — the Claude Code twin of .codex/config.toml)
--update also removes files the template no longer ships when they are still byte-identical to what was
installed (pristine); an edited copy is kept and listed.
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
import re
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


def _norm_hash(rel, path):
    """Hash for classification. `.codex/config.toml` is compared without the top-level `model` /
    `model_reasoning_effort` lines that `ks` writes for the main session (3.2.0), so they never count as
    a local edit; the refresh keeps them (see the copy loop)."""
    if rel.replace(os.sep, "/") == ".codex/config.toml":
        with open(path, encoding="utf-8") as fh:
            body = "".join(l for l in fh if not re.match(r'^(model|model_reasoning_effort)\s*=', l))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
    return sha256(path)


def _model_lines(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [l for l in fh if re.match(r'^(model|model_reasoning_effort)\s*=', l)]
    except OSError:
        return []


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


def _operator_name():
    """Operator from the hooks' resolution (user.toml / TKSFW_USER / git), or None — best effort."""
    try:
        sys.path.insert(0, os.path.join(TEMPLATE, ".agents", "hooks"))
        import hooklib as H
        return H.operator_source()[0] or None
    except Exception:
        return None


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
    ap.add_argument("--drift", action="store_true", help="report the project's framework files against this version; exit 1 on drift; writes nothing")
    ap.add_argument("--json", action="store_true", help="with --drift: machine-readable output")
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
    if a.drift:
        if prev is None:
            sys.exit(f"{target} carries no .agents/.tksfw.json — not a TKSfw project")
        pm = prev.get("plugin_mode", False)
        rep = {"version_project": prev.get("version"), "version_installed": version(), "plugin_mode": pm,
               "enabled": prev.get("enabled", True) is not False, "unchanged": [], "outdated": [], "edited": [], "missing": []}
        ph = prev.get("files", {})
        for rel in template_files(pm):
            dst = os.path.join(target, rel)
            h = sha256(os.path.join(TEMPLATE, rel))
            if not os.path.exists(dst):
                rep["missing"].append(rel)
            elif _norm_hash(rel, dst) == h:
                rep["unchanged"].append(rel)
            elif ph.get(rel) == _norm_hash(rel, dst):
                rep["outdated"].append(rel)            # untouched locally, newer in this version
            else:
                rep["edited"].append(rel)              # edited locally (merge by hand)
        drift = bool(rep["outdated"] or rep["edited"] or rep["missing"]) or rep["version_project"] != rep["version_installed"]
        rep["drift"] = drift
        if a.json:
            print(json.dumps(rep, indent=2))
        else:
            print(f"project v{rep['version_project']} · installed v{rep['version_installed']} · "
                  f"{'plugin' if pm else 'full'} mode · {'armed' if rep['enabled'] else 'DISARMED'}")
            for k in ("outdated", "edited", "missing"):
                if rep[k]:
                    print(f"  {k}: {len(rep[k])}")
                    for r in rep[k][:40]:
                        print(f"    {r}")
            print(f"  unchanged: {len(rep['unchanged'])}")
            print("no drift" if not drift else "DRIFT — `--update` refreshes outdated files; edited ones need a manual merge")
        sys.exit(1 if drift else 0)
    if prev and not a.update:
        sys.exit(f"{target} already carries TKSfw v{prev.get('version')} — use --update to refresh it")
    if a.update and prev:
        plugin_mode = prev.get("plugin_mode", False) if not a.plugin_mode else True
    else:
        plugin_mode = a.plugin_mode
    prev_hashes = (prev or {}).get("files", {})

    # 3.0.0: .agents/models.toml → .agents/config.toml. Rename the operator's file (content untouched, so
    # pins, HIL and limits survive) and carry its recorded hash over, then let the normal loop classify it.
    old_cfg, new_cfg = os.path.join(target, ".agents", "models.toml"), os.path.join(target, ".agents", "config.toml")
    migrated_cfg = False
    if os.path.isfile(old_cfg) and not os.path.exists(new_cfg):
        os.replace(old_cfg, new_cfg)
        if ".agents/models.toml" in prev_hashes:
            prev_hashes[".agents/config.toml"] = prev_hashes.pop(".agents/models.toml")
        migrated_cfg = True

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
        cur = _norm_hash(rel, dst)
        if cur == h:
            unchanged.append(rel)
        elif rel in prev_hashes and prev_hashes[rel] == cur:
            keep_lines = _model_lines(dst) if rel.replace(os.sep, "/") == ".codex/config.toml" else []
            shutil.copy2(src, dst)                     # untouched since install: safe to refresh
            if keep_lines:                             # re-insert the ks-written main-session model lines
                body = open(dst, encoding="utf-8").read().splitlines(keepends=True)
                idx = next((i for i, l in enumerate(body) if l.startswith("[")), len(body))
                body[idx:idx] = keep_lines
                open(dst, "w", encoding="utf-8").write("".join(body))
            refreshed.append(rel)
        else:
            kept.append(rel)                           # locally edited (or pre-existing): never overwrite

    removed, retired_kept = [], []
    for rel, h in prev_hashes.items():                 # files the template no longer ships (2.7.0)
        if rel in new_hashes:
            continue
        dst = os.path.join(target, rel)
        if not os.path.exists(dst):
            continue
        if sha256(dst) == h:
            os.remove(dst)
            removed.append(rel)
            d = os.path.dirname(dst)
            while d != target and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
        else:
            retired_kept.append(rel)

    manifest = {"framework": "TKSfw", "version": version(), "plugin_mode": plugin_mode,
                "enabled": (prev or {}).get("enabled", True) is not False, "files": new_hashes}
    for keep in ("resets", "layers", "installs"):          # generation history (ks project reset); layer paths (ks layers pin); install log
        if (prev or {}).get(keep):
            manifest[keep] = prev[keep]
    # install log (2.5.0): every init/update is recorded here; the first session afterwards is told to log
    # it in changes.yaml (Layer CORE) — the operator has nothing to write by hand
    import datetime as _dt
    manifest.setdefault("installs", []).append({"ts": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "version": version(),
                                                "action": "update" if prev else "init", "mode": "plugin" if plugin_mode else "full",
                                                "operator": _operator_name()})
    manifest["installs"] = manifest["installs"][-20:]
    mp = os.path.join(target, MANIFEST_REL)
    os.makedirs(os.path.dirname(mp), exist_ok=True)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"TKSfw v{manifest['version']} → {target}  ({'plugin' if plugin_mode else 'full'} mode)")
    if migrated_cfg:
        print("  renamed: .agents/models.toml → .agents/config.toml (content kept; routing pin, HIL and limits survive)")
    for label, items in (("installed", installed), ("refreshed", refreshed), ("kept (edited locally)", kept),
                         ("removed (retired by the template, pristine)", removed), ("retired but edited locally — delete by hand", retired_kept)):
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
    action = "update" if prev else "install"
    print(f"\nRecorded: {action} of v{manifest['version']} in .agents/.tksfw.json — the first session logs it in "
          "changes.yaml (Layer CORE); nothing to write by hand.")
    print("\nNext steps")
    if plugin_mode:
        print("  1. Launch Codex (or Claude Code) in this folder. Codex asks once to trust the project's .codex layer — accept.")
        print("  2. `ks doctor` here: 0 FAIL means the project is ready. Hooks run from the installed plugin, so there is")
        print("     nothing to re-trust for this project unless the framework itself was upgraded (doctor says so).")
    else:
        print("  1. Launch Codex (or Claude Code) in this folder. Codex asks to trust the project's .codex layer — accept —")
        print("     and lists the project's hooks: type /hooks and trust them (full mode ships its own hooks).")
        print("  2. `ks harness retrust --ack` to record that trust, then `ks doctor` — 0 FAIL means ready.")
    print("  3. Optional: describe the project in KS_PROJECT.md (archetype) / KS_SPEC.md (project spec).")
    print("  4. Start the run with the ks-start skill: Codex `$ks-start` (or /skills → ks-start); Claude Code `/tksfw:ks-start` (`/ks-start` when unambiguous).")
    if kept:
        print(f"\nReview the {len(kept)} locally edited file(s) against template/ and merge by hand.")


if __name__ == "__main__":
    main()
