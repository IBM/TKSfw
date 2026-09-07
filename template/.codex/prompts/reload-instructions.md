---
description: Reload the instruction layers (AGENTS.md, KS_PROJECT.md, KS_SPEC.md) after they have been updated.
---

Please reload the instruction layers — `AGENTS.md` (method) and the project layers listed in the session-start block (`KS_PROJECT.md` L3, `KS_SPEC.md` L4, or the paths declared under `layers` in `.agents/.tksfw.json`). I have updated them.

Re-read every file fresh from disk (do not rely on what was auto-loaded at session start; run `ks layers resolve` to see which layer changed), then briefly confirm what changed versus your prior understanding before continuing. L4 overrides L3; neither overrides AGENTS.md.
