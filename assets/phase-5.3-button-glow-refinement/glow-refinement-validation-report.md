# Phase 5.3 portfolio button glow refinement

## Change

- Created a separate copy of the current Phase 5.2 composition. The Phase 5.2 files and the original `assets/image.png` were not modified by this generator.
- Replaced the existing glow layer's transparent PNG and opacity curve. Omitted the prior separate moving border reflection from this copy to keep the button free of beams. The source button, border gradient, fill, text, arrow, dimensions, terminal cursor layers, and original background layer remain unchanged.
- The halo colors come from bright cyan-to-violet pixels selected from the existing rounded border. Gaussian blur softens those source pixels; a rounded-rectangle signed-distance mask clips every halo pixel to the outside of the button contour. No second outline or new geometry is drawn.
- Glow opacity breathes smoothly from 12% to 30% over 3.0 seconds. The three-second cycle divides the existing nine-second composition exactly, so the loop closes without a jump.

## Validation

- Original image SHA-256: `50d22010771a31d20a9bdd051d2b0baff121fa723fb8b28f99e3c0c408821c8f`. The source and the source-identical static preview are both 1672×941.
- The halo source mask covers the four border sides: `{'top': 3267, 'right': 644, 'bottom': 3383, 'left': 644}`; rounded corners: `{'top_left': 2210, 'top_right': 2353, 'bottom_left': 2474, 'bottom_right': 2242}`.
- Added overlay pixels inside the rounded button contour: **0**. This leaves the button fill, text, and arrow clean.
- The animated preview is 1000×563, matching the README display width. At the trough, 3649 pixels in the button detail region change by more than 10 channel levels; the peak maximum channel difference is 43.
- Lottie validation confirms the original-background layer is unchanged; all retained layers match the Phase 5.2 source copy except the refined glow. The prior moving border-reflection layer is omitted only from this copy. The composition remains 1672×941 at 30 fps for 9 seconds.
- The SVG keeps the same canvas and existing animation layers; only the glow image data and glow opacity cycle change.

## Deliverables

- `profile-banner-phase-5.3.json` — self-contained Lottie JSON.
- `profile-banner-phase-5.3.svg` — same-canvas animated SVG.
- `preview/profile-banner-phase-5.3.png` — full-color animated PNG at README display size, avoiding GIF palette artifacts.
- `preview/profile-banner-phase-5.3-static.png` — exact original artwork without animation.
- `preview/portfolio-button-outer-halo-detail-peak.png` — enlarged still of the halo at peak intensity.
- `layers/portfolio-button-outer-halo.png` — transparent, outside-only glow overlay.
