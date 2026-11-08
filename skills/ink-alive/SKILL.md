---
name: ink-alive
description: InkAlive (妙笔生动) creates, repairs, and inspects short single-shot illustrated character GIFs using native image generation and a reproducible local frame pipeline. Use for 漫画动图, character acting loops, flicker repair and expression/action continuity. Not a talking-avatar, pet-installation or complete multi-shot film workflow.
---

# InkAlive · 妙笔生动

Produce one intelligible character action with stable art and coherent expression, using the user-approved Panna effect as a visual benchmark. Preserve the current project's character references and explicit user choices. The benchmark is a result standard, not a universal pose/count/size template.

Read [production contract](references/contract.md) before production. Inspect `assets/reference/panna-approved.gif` and its `approval.json` when choosing the quality target. Do not infer acceptance of a new output from acceptance of this reference.

## Choose the work

- New drawing/pose or a demonstrated raster defect: use built-in imagegen. Read [generation and repair](references/generation.md), inspect actual references and retain exact prompts/receipts. Do not silently use an API/model fallback.
- Existing accepted art needing background/texture/motion finishing: keep its artwork and edit only the demonstrated issue through the local helper.
- Long action, large occlusion or unreliable intermediate anatomy: improve drawn keys or split the action. Do not force the portrait profile over unrelated motion or interpolate across shots.

Start with one short GIF. Record intended entry/action/exit, camera, identity, moving/idle regions, timing and loop before generation. Inspect every source cell. Fix identity/anatomy/props before local finishing; script success does not repair incorrect source acting.

## Local tool

Use `python scripts/gif_tool.py --help`. See [recipe/CLI reference](references/recipe.md) for configurable inputs, coordinates and review records. Dependencies are listed in `requirements.txt`; use an existing environment when available.

Create a project with `init`, generate its art, inspect source grid/alpha and configure `project.json`. Source sheet extraction and ordinary encoding are defaults. Enable fixed-background repair, idle-torso/head stabilization or dense expression in-betweens only when justified by the actual shot.

```
python scripts/gif_tool.py init /absolute/new-project --name character-nod
python scripts/gif_tool.py render /absolute/new-project/project.json --out /absolute/new-project/render-v1
```

Every output directory is new. Keep source art and old versions. The tested full example can be reproduced with:

```
python scripts/gif_tool.py render assets/panna/project.json --out /absolute/panna-rebuild-v1
```

For another character/view, replace references, art, action and coordinates; the script does not detect a face or know which torso should stay still. Do not resize Panna's coordinate profile blindly. Use a single fixed background plate and process masks as alpha only when extraction changes accepted RGB. Preserve full animated head contours and inspect the neck join.

## Inspect, select, deliver

View `preview.gif`, actual decoded review sheets and the approved reference at native size. Inspect changing eyes/eyelids, lips, hair, hands/props, grounding and the loop. Compare fixed regions and key-time checks separately from natural acting. Distinguish drawn keys from inferred image samples and encoded frames; more fps is not a quality verdict.

The helper always leaves visual/playback review pending. Fill a SHA-bound review record only after actual inspection. Use `record-review`, then `finalize` when required visual checks and observed playback or explicit exact-artifact user acceptance exist. These are agent verification steps, not a request for repeated user permission. If a needed view is unavailable, deliver an honestly labeled preview with the exact limitation; do not invent a passed review.

Show the selected GIF inline with a usable file link, a concise change/limit note and the project/check record. Keep rejected experiments apart. Update the current project's continuity files as required there. Do not publish, upload or extend to a film/batch from this skill invocation alone.
