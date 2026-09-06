#!/usr/bin/env python3
"""Method-bound integrity/hygiene checks (Group A: policy + method).

Enforces the domain-agnostic `AGENTS.md § Core Acceptance Criteria` that are NOT tied to any
deliverable's meaning: no internal-alias leakage into outputs, and a clean workspace. It is
deliberately free of archetype/project concepts (no D-numbers, no ARR, no catalog, no regions) —
those domain checks live in the Group-B `verify-deliverables` skill.

Both the file set to scan and the alias strings are DATA INPUTS, not hardcoded: the *rule* ("don't
leak internal input aliases into any deliverable") is method (A); the *specific aliases* (e.g. a
project's codenames) are instance data (L4) supplied by the caller. This mirrors how
`register-deliverables` keeps the mechanism generic and the naming external.

Usage:
    python3 integrity_checks.py [--files f1 f2 ...] [--aliases A B ...] [--root .] [--require-aliases]
      --files            explicit files to scan for alias leakage (default: discover document
                         deliverables from .claude/workarea/deliverables.yaml; else the legacy
                         D*.md/D*.yaml glob)
      --aliases          internal alias strings that must NOT appear in any scanned file (default: none)
      --root             directory to walk for the clean-folder scan (default: current dir)
      --require-aliases  treat an empty alias list as a FAILURE, not a skip. Use when the project
                         is known to have internal aliases (L4 data), so the leak check can never
                         silently no-op. Without it, an empty list emits a visible WARN and passes.

Exit 0 = clean, 1 = problems. Std lib only.
"""
import sys, os, glob
sys.dont_write_bytecode = True  # never leave __pycache__ in the workspace we're checking

HERE = os.path.dirname(os.path.abspath(__file__))
# .../verify-integrity/assets -> .../yaml-log-entry/assets (shared pyyaml-optional parser)
VALIDATOR_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "yaml-log-entry", "assets"))
REGISTRY = os.path.join(".claude", "workarea", "deliverables.yaml")


def _argvals(args, flag):
    """Collect the values following `flag` up to the next --option (or end)."""
    if flag not in args:
        return None
    out, i = [], args.index(flag) + 1
    while i < len(args) and not args[i].startswith("--"):
        out.append(args[i]); i += 1
    return out


def discover_document_files():
    """Document deliverables (.md/.yaml) from the registry, else the legacy D* glob.
    Returns a sorted list of relpaths. Never scans code/binaries."""
    files = None
    if os.path.exists(REGISTRY):
        try:
            if VALIDATOR_DIR not in sys.path:
                sys.path.insert(0, VALIDATOR_DIR)
            from validate_yaml_log import load_entries
            entries, _ = load_entries(REGISTRY)
            files = []
            for _did, fields in entries:
                if not isinstance(fields, dict):
                    continue
                p = fields.get("Path")
                pats = [p] if isinstance(p, str) else (p if isinstance(p, list) else [])
                for pat in pats:
                    if isinstance(pat, str):
                        files += [m for m in glob.glob(pat, recursive=True) if os.path.isfile(m)]
        except Exception:
            files = None
    if files is None:
        files = glob.glob("D*.md") + glob.glob("D*.yaml")
    return sorted({f.replace("\\", "/") for f in files if f.lower().endswith((".md", ".yaml"))})


def main():
    args = sys.argv[1:]
    files = _argvals(args, "--files")
    aliases = _argvals(args, "--aliases") or []
    root = (_argvals(args, "--root") or ["."])[0]
    require_aliases = "--require-aliases" in args
    fails = []

    if files is None:
        files = discover_document_files()
        print(f"[scan] {len(files)} document deliverable(s) discovered")
    else:
        print(f"[scan] {len(files)} file(s) from --files")

    # 1) alias leakage — no internal input alias may appear in any scanned deliverable
    if aliases:
        for f in files:
            try:
                v = open(f, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            hits = [a for a in aliases if a in v]
            if hits:
                fails.append(f"alias leakage in {f}: {hits}")
    elif require_aliases:
        fails.append("no --aliases supplied but --require-aliases is set: the alias-leak check "
                     "cannot run. Pass the project's internal aliases (from _project.md § INPUTS).")
    else:
        print("[alias] WARN — no --aliases supplied; alias-leak check did NOT run. "
              "Pass --aliases (and --require-aliases to enforce) if this project has internal aliases.")

    # 2) clean folder — no build/editor/office temp artifacts anywhere under root
    junk = []
    for r, dirs, fs in os.walk(root):
        if "/.git" in r:
            continue
        if os.path.basename(r) == "__pycache__":
            junk.append(r)
        for fn in fs:
            if fn == ".DS_Store" or fn.endswith((".pyc", ".tmp")) or fn.startswith("~$"):
                junk.append(os.path.join(r, fn))
    if junk:
        fails.append(f"temp artifacts present ({len(junk)}): "
                     + ", ".join(junk[:8]) + ("…" if len(junk) > 8 else ""))

    print("\n" + ("PASS — no integrity/hygiene issues" if not fails else "FAIL:"))
    for x in fails:
        print("  -", x)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
