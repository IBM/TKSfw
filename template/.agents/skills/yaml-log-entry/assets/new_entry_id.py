#!/usr/bin/env python3
"""Generate a fresh entry ID + timestamp for a project YAML ledger.

Why compute these instead of writing them by hand: an LLM is a poor RNG (biased, can
repeat) and has no authoritative clock. The ID is uniform base62 via `secrets`, checked
for uniqueness against the target file's existing IDs; the timestamp is the real current
local time in the `references/schemas.md` format. Emitted by the same rules `validate_yaml_log.py`
enforces, so a generated entry passes validation on the first try.

Entries in every ledger are shaped as a YAML list of single-key mappings where the ID is
the KEY (`- 7Kd2Rf9Q:` / `- 3pQ9mK2v-BEGIN:`). This script reads those keys to guarantee
the new ID is not already present.

HandoffIDs are composite: `<base62-8>-<BEGIN|END>`. The base62 stem binds the BEGIN and
END halves of one handoff. Use `--handoff BEGIN` / `--handoff END`:
  * BEGIN mints a NEW stem not already used by any handoff in the file.
  * END reuses an existing stem: pass `--stem <base62-8>` (the stem minted at BEGIN) so the
    two halves share an ID; without --stem a new unique stem is minted.

Usage:
    python3 new_entry_id.py [logfile]                       # changes/lessons/events
    python3 new_entry_id.py handoffs.yaml --handoff BEGIN    # -> <stem>-BEGIN
    python3 new_entry_id.py handoffs.yaml --handoff END --stem <stem>   # -> <stem>-END
Output: "<ID>\\t<YYYY-MM-DD hh:mm:ss>"  (tab-separated, one line)
Needs:  stdlib only. Uses pyyaml to read existing IDs if importable, else a line scan.
"""
import sys
import re
import secrets
import argparse
from datetime import datetime

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"  # base62
# Top-level list entry whose key is the ID (optionally with a -BEGIN/-END handoff suffix).
KEY_LINE = re.compile(r'^\s*-\s+["\']?([0-9A-Za-z]{8}(?:-(?:BEGIN|END))?)["\']?:\s*$')


def existing_ids(path):
    """Best-effort set of entry-id KEYS already in the ledger.

    Uses pyyaml when importable; falls back to a line scan so the generator never
    hard-depends on pyyaml just to stay unique.
    """
    try:
        text = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return set()
    try:
        import yaml
        data = yaml.safe_load(text) or []
        ids = set()
        for item in data:
            if isinstance(item, dict):
                ids.update(str(k) for k in item.keys())
        return ids
    except ImportError:
        return {m.group(1) for m in (KEY_LINE.match(l) for l in text.splitlines()) if m}


def stems(ids):
    """Base62 stems (BEGIN/END suffix stripped) — used to keep handoff pairs unique."""
    return {i.rsplit("-", 1)[0] if i.endswith(("-BEGIN", "-END")) else i for i in ids}


def gen_stem(used_stems):
    while True:
        s = "".join(secrets.choice(ALPHABET) for _ in range(8))
        if s not in used_stems:
            return s


def main():
    ap = argparse.ArgumentParser(description="Mint a ledger entry ID + timestamp.")
    ap.add_argument("logfile", nargs="?", help="target ledger; enforces ID uniqueness")
    ap.add_argument("--handoff", choices=["BEGIN", "END"],
                    help="mint a composite HandoffID <stem>-STATE")
    ap.add_argument("--stem", help="reuse this base62 stem (for the END half of a handoff)")
    args = ap.parse_args()

    ids = existing_ids(args.logfile) if args.logfile else set()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if args.handoff:
        if args.stem:
            if not re.fullmatch(r"[0-9A-Za-z]{8}", args.stem):
                ap.error("--stem must be 8-char base62")
            stem = args.stem
        else:
            stem = gen_stem(stems(ids))
        print(f"{stem}-{args.handoff}\t{ts}")
    else:
        print(f"{gen_stem(stems(ids))}\t{ts}")


if __name__ == "__main__":
    main()
