# Native PNG keys and fixed-background HD previews

Use this path when a dense sheet cannot supply enough per-frame detail, or when native-color PNG masters and a declared pixel budget are required. The legacy sheet/GIF path remains in `gif_tool.py`; its252-pixel reference establishes acting/stability, not a universal production size.

## Source preparation

Choose the actual delivery composition, largest subject display size and camera crop/zoom first. Inspect returned image dimensions and usable per-cell pixels. Generate individual drawings or smaller batches with built-in imagegen. Preserve original RGB PNGs. If the tool returns fewer pixels than requested, record the actual size; do not upscale and relabel it as native detail. Native outpaint tiles may extend a canvas while retaining an adequately detailed subject at1:1; inspect their real seams and record all downscaling/compositing.

For a fixed camera, composite every key over one real background plate and intentionally idle body layer. Masks and native coordinates belong to the actual drawings. Use extracted alpha without replacing accepted RGB. Check neck/collar joins before interpolation; a head cutout can leave holes or duplicate collars. End any transition in exposed neck skin and preserve canonical clothing. Do not freeze a body that should be acting.

## Recipe

`scripts/png_motion.py` reads an explicit ordered list of fully composed opaque RGB PNGs. Paths and provenance files are relative to the recipe. Reusing a PNG for a deliberate return/hold does not create a new drawing.

```json
{
  "frames": ["keys/down.png", "keys/up.png", "keys/nod.png", "keys/up.png"],
  "durations_ms": [480, 480, 480, 560],
  "minimum_source_size": [1920, 1080],
  "moving_roi": [112, 0, 912, 740],
  "provenance_evidence": ["source-detail-record.json"],
  "loop": true,
  "interpolate": {"step_ms": 40, "eyes": []}
}
```

These coordinates/sizes illustrate one portrait shot. Configure them for each job; they are not face detection or a required aspect ratio. Source canvases must be equal, opaque and at least the declared dimensions. Every pixel outside `moving_roi` must match across keys. Only the moving crop enters optical flow; full-size RGB frames are written individually. `max_crop_bytes` optionally limits the crop-frame buffer (default512MiB), not all process memory. The helper does not resize source PNGs. Header/provenance checks cannot detect an image dishonestly enlarged before input.

Closed-to-open eyes reveal new geometry. Add real drawn phases instead of trusting dense flow to invent pupils. Optional `eye_opening_states` supplies one inspected phase label per timed key. Each entry in `interpolate.eyes` then requires `centers:[[x,y],...]` in crop-local pixels, plus an `ellipse`, `white_box` and optional `feather_px`. For transitions between different declared phases, the helper uses a nearest actual drawn eye with interpolated rigid translation. Optional `occlusion_face_patch:[cx,cy,rx,ry]` retains one coherent drawn face region when separate eye patches would split eyebrows. This mode holds drawn occlusion states rather than claiming newly drawn in-betweens; it still needs actual visual review. Matching phase labels retain ordinary motion interpolation. No setting is an automatic anatomy detector.

## Commands and outputs

```sh
python scripts/png_motion.py render /absolute/project.json --out /absolute/render-v1
python scripts/png_motion.py prepare-review /absolute/render-v1
python scripts/png_motion.py record-review /absolute/render-v1 --record /absolute/review.json
python scripts/png_motion.py finalize /absolute/render-v1 --out /absolute/selected-v1
```

Choose new render/selection directories. Rendering writes original-color `frames-native/`, native source keys, a separate256-color `preview.gif`, source/evidence hashes, timing/static/key checks and decoded review sheets. Native source-key RGB is preserved at declared timestamps. GIF keys are checked against palette-quantized sources; GIF is not claimed to preserve all source colors. Full-frame HD GIFs can be large; use native PNGs for video editing rather than repeatedly decoding/re-encoding GIFs.

`prepare-review` independently checks actual native frame hashes/key pixels and the decoded GIF clock, static pixels, opaque shared-palette/full-frame/no-clear structure. It creates a manifest binding all native masters and a pending review template. Do not pass an unprepared native run directly to legacy review commands.

Review the usual identity/anatomy, stability, expression/action, edges/props and loop, plus `native_detail` at actual display size. Record native evidence inside the run. `record-review` binds it to the GIF and complete native manifest. `finalize` reuses the existing exact-artifact playback/user-acceptance gate, requires passed native-detail review, and includes the bound PNG masters. A frame sheet is not a continuous playback judgment. Missing playback or failed art remains a preview; no acceptance is inferred from the old benchmark.
