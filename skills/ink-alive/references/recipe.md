# Recipe and local CLI

Requirements: Python3.10+, Pillow, numpy, opencv-python. No GPU, token or network is required by the helper. Native imagegen is used separately for art. Preserve supported dependency versions in the output manifest; pixel reproduction is environment-specific, not a cross-platform guarantee.

Run `python scripts/gif_tool.py --help` for commands. Paths inside recipes resolve relative to the recipe file, so projects can move as a unit. Every render output directory must be new; source files and earlier results are never overwritten. Missing inputs/config errors fail before creating render outputs.

```
python scripts/gif_tool.py init /absolute/new-project --name character-nod --columns 6 --rows 4
# Generate and inspect source-sheet.png; edit project.json timing/profile.
python scripts/gif_tool.py render /absolute/new-project/project.json --out /absolute/new-project/render-v1
python scripts/gif_tool.py inspect /absolute/new-project/render-v1/preview.gif --out /absolute/new-project/inspection-v1
python scripts/gif_tool.py record-review /absolute/new-project/render-v1 --record /absolute/review.json
python scripts/gif_tool.py finalize /absolute/new-project/render-v1 --out /absolute/new-project/selected-v1
```

`render` exports source, repaired and stabilized key PNGs, final GIF, actual decoded review sheets, SHA/input/version manifest and checks.json. Frame/static/key checks run on the actual output; visual review starts pending. `inspect` decodes an existing GIF into frames/contact sheets and reports actual structure, independent of render assumptions. New directories only.

## Root fields

- `schema_version`:1; `id`:human-readable asset ID.
- `source.kind`: `sheet` or `gif`; `source.path` is required. Sheet needs `grid:[cols,rows]`, optional `cells` selection, `edge_trim`, and `durations_ms` for selected cells. All cells are extracted to the same native size. GIF retains its actual timings and must use a shared-color set; unknown input palette colors are rejected rather than silently reducing approved keys.
- Durations are positive GIF centiseconds, at least20ms. The source key count, loop, dimensions and durations are recorded separately from final encoded fps.
- `loop`:true for a genuine loop, false for one-shot playback. Loop neighbor wrapping is only used when true.
- `background.mode`: `preserve` or `fixed`. Fixed background and stabilization require sheet input. Fixed needs `matte` and `target_rgb`, optional `alpha_clip:[100,200]`. `ink_support` is optional and source-specific: `red_range:[235,245]`, `radius:4` for the pale-paper example. The target is mapped once to an existing global palette entry, then reused everywhere; actual RGB is reported.
- `stabilize.enabled`:false by default. Enabling requires `torso_idle:true`, a foreground matte/fixed background, `head_matte`, and explicit `coordinate_size:[w,h]` matching extracted cells. Coordinates are pixels in that size, never guessed or resized silently. Set `master`, `head_clip_y`, `ink_max_y`, `torso_transition_y:[start,end]`, `protected_ellipses:[[cx,cy,rx,ry],...]`, `hair_region:{upper_y,left_x,right_x,lower_y}` and `reference_strength` from actual art. Do not reuse Panna's eye/neck coordinates for another view/character.
- `interpolate.enabled`:false by default. `step_ms` is a positive centisecond interval, at least20ms. Total duration and every source-key timestamp must divide exactly by the interval; otherwise choose compatible timing explicitly. No hidden retiming is performed. `eyes` optionally provides `ellipse` and `white_box` per eye, with optional `feather_px`; light-sclera visibility selection is a heuristic requiring inspection. An empty list uses a single nearest warped drawing without eye-specific selection.

The bundled `assets/panna/project.json` is a tested full-pipeline recipe, not a universal default. To repeat only accepted GIF continuity work, use `source.kind:gif`, disable fixed-background/stabilization and enable interpolation with inspected eye regions.

Head extraction can specify `stabilize.head_alpha_clip`. Fine-ink recovery is enabled only with explicit `stabilize.head_ink_support:{red_range,radius}`; `ink_max_y` limits it to the head. As with background ink support, this is source-specific. The pale-paper example supplies it explicitly; leave it disabled for unrelated colors until inspected.

## Visual review record

Write review JSON only after actually viewing the indicated output. `render` writes a pending `review-template.json`; inspect images before completing it. Every required check has `status:passed` and a concrete note: `identity_anatomy`, `stability`, `expression_action`, `edges_props`, `loop_join`. The record must include the output `artifact_sha256`, nonempty `evidence` paths to inspected local files, reviewer and `playback.status`.

`playback.status` is `observed`, `unavailable` or `not_performed`. Only `observed` permits agent-reviewed finalization. A user may explicitly accept an exact SHA despite unavailable independent playback: provide `user_acceptance:{confirmed:true,artifact_sha256,statement}` based on an actual user message, never a default or inferred consent. `record-review` binds the record and evidence hashes to the rendered artifact. `finalize` rechecks the GIF, mechanical result, review/evidence hashes and benchmark reference hash before copying selected output. It does not ask the user for routine permission and does not make a false machine-quality guarantee.

Reports/reference approval are attestations with evidence, not classifiers that prove truthful visual review. If review cannot be completed, deliver `preview.gif` clearly labeled as a preview with the specific missing check, without marking it approved.
