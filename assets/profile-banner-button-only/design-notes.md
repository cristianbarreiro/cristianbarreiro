# Portfolio button-border-only variant

## Composition

- `profile-banner-button-only.svg`: self-contained animated SVG with the original PNG embedded byte-for-byte.
- `profile-banner-button-only.json`: self-contained Lottie composition with one unchanged image layer and one native rounded-border shape layer.
- `preview/profile-banner-button-only.gif`: 9-second optimized animated preview; a visible cyan-to-violet highlight travels only along the Explore My Portfolio border.
- `preview/profile-banner-button-only-static.png`: representative frame at 2.25 seconds.
- `preview/preview.html` and `preview/lottie-preview.html`: local SVG and Lottie-Web previews.

## Motion scope

The only animated effect is a visible cyan-to-violet reflection moving around the existing 13 px rounded button border. Its color shifts from cyan on the left to blue and violet on the right to blend with the existing edge. A 190 px highlight and fine bright core travel directly along the contour, with round caps and the border's cubic corner curves carrying it through each turn instead of rotating it as a rectangle. The README embeds the GIF because its frame-based animation remains visible in GitHub's Markdown renderer. The original circuit lines, ring, typography, icons, terminal, and remaining artwork stay as they are in the static source image; no circuit-light effects are added.

## Checks

- Original source: `assets/image.png`; SHA-256 `50d22010771a31d20a9bdd051d2b0baff121fa723fb8b28f99e3c0c408821c8f`.
- The PNG embedded in the SVG and Lottie file matches the source bytes exactly.
- The SVG parses as XML and contains only two button-border strokes.
- The GIF retains 180 frames, lasts 9 seconds, and keeps all frame-to-frame changes inside the button region after decoding.
- Lottie contains 2 layers: one native vector border effect and the original image.
- Pixels outside the button area match the static source in the generated preview.
- Opening and closing frames are identical at preview size; no loop seam is visible.
- Preview: 180 frames at 50 ms each; SVG 1,896,478 bytes; Lottie 1,907,169 bytes; GIF 320,432 bytes.
- Generation time: 18.6 seconds.
