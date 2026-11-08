# Native-image generation and repair

Use imagegen for art. Inspect current identity masters before prompting; project AGENTS/character decisions override this example. Keep the existing human/animal identity, body/outfit/accessories and original acting references. The bundled Panna files illustrate one approved character; follow the current project's identity and costume decisions rather than importing this example's cast or style into unrelated work.

## One clear shot

Ask for an equal-cell static sequence sheet when native motion is not actually returned. Declare grid, order and actual incremental motion, fixed camera/light/scale and stationary background. Specify one intelligible action with gradual phases and clean anatomy. Use enough real intermediate drawings for the motion before software interpolation, but choose density by the action rather than a universal target count. Ask for first/last state matching only for an intentional loop. Preserve source art and inspect every cell, not only the prompt.

Suggested prompt skeleton:

```
Use case: illustration-story. One fixed-camera character action sequence.
Input1 is the approved identity/style reference, not a collage layout to copy.
Return an equal-cell [columns]x[rows] sheet in row-major order, no text/gutters.
Action: [entry state -> gradual action -> exit state].
Keep: [identity, scale, camera/axis, outfit, props, light].
Moving regions: [...]. Idle regions: [...].
Avoid omitted motion phases, duplicate limbs/props, camera drift and face redesign.
```

The actual generation output may have fewer details, wrong grid or repeated poses. Check cell boundaries and extracted poses, then fix the demonstrated defect with imagegen. Do not silently reinterpret wrong output as correct.

## Alpha extraction, preserving accepted artwork

Ask imagegen for genuine transparency while retaining exact canvas/cell order/positions. Use its alpha only when it repaints accepted colors/expressions. The helper accepts grayscale alpha sheets or RGBA output; it never uses a cutout's new RGB.

Whole-foreground extraction: preserve character, clothing, fine ink/strands and opaque skin; remove only empty background, including hair gaps. Inspect matte size and holes. Keep one fixed plate in the compositor; repeated identical-background prompts are insufficient.

Head/neck processing extraction: preserve head/hair/ears/exposed neck, remove background and clothing. Inspect neck/collar placement and thin hair. A precision head cutout can still damage contours. The tested recipe retains the full upper image and uses the head mask for processing/neck protection, transitioning into a canonical idle torso near the collar.

For the pale-paper Panna example, red-channel ink support helps retain fine outlines after a soft extraction. This is a configurable source-specific keying assumption, unsuitable for arbitrary backgrounds. Disable or recalibrate it rather than applying the same threshold to every picture.

## Failed approaches to avoid repeating

- Container fps or increased change count does not prove fluid acting.
- Repainting the whole scene to fix motion changes framing/identity and destroys a controlled comparison.
- Global temporal blur can soften facial detail while leaving redraw/shape drift.
- Coarse block interpolation and double-image dissolves can create doubled pupils/lips/nose.
- Gifski/Gifsicle are useful encoders/manipulators, not guaranteed generative-continuity solvers. Imported skills are references, not an authorization to change frame counts, timing or user assets.

Prior research: [Gifsicle manual](https://github.com/kohler/gifsicle/blob/master/gifsicle.1), [Anthropic GIFBuilder](https://github.com/anthropics/skills/blob/main/skills/slack-gif-creator/core/gif_builder.py), [Gifski API](https://github.com/ImageOptim/gifski/blob/main/gifski.h), [All-In-One-Deflicker](https://github.com/ChenyangLEI/All-In-One-Deflicker). This skill ships original local helper logic and no downloaded executable/model or copied third-party skill implementation.
