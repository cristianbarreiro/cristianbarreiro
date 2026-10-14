# Phase 5.2 microinteraction validation

## Source and scope

- Original artwork: `assets/image.png`, SHA-256 `50d22010771a31d20a9bdd051d2b0baff121fa723fb8b28f99e3c0c408821c8f`. It was not edited; the same PNG bytes are embedded in the new Lottie and SVG.
- Active source composition: `assets/profile-banner-button-only/profile-banner-button-only.json`. This is the current full-canvas Lottie in the working tree, with the original artwork and the existing portfolio-border reflection.
- The prior `phase-5.1-motion-refinement` source is absent from the latest working tree. Its older ring/circuit effects were not restored, because the current selected design keeps circuit lighting off.
- The current border-reflection layer was copied unchanged. The README and currently published asset remain untouched for this phase.

## Effects and layers

- `portfolio-button-ambient-glow-from-existing-border`: localized, two-radius soft bloom extracted from bright, color-saturated pixels along all four sides and rounded corners of the existing button border. Its opacity stays present between 34% and 100% on a 3.0-second loop; both alpha masks are blurred, so no second crisp outline is drawn.
- `terminal-cursor-blink-at-original-underscore`: original 14×3 px cyan cursor at `[1149, 384, 1163, 387]`; it blinks on a 1-second cycle with short fades.
- `terminal-cursor-local-background-repair`: changes only `[1146, 380, 1167, 391]` to estimate the hidden dark terminal background from adjacent pixels. The surrounding source crop is otherwise unchanged; the source underscore is fully removed underneath the animated cursor.
- `portfolio-button-rounded-border-reflection`: preserved from the active composition without changes.
- `unchanged original banner`: original PNG, unchanged and embedded.

## Validation results

- The static preview has the original image dimensions (1672×941) and is pixel-identical to the source.
- The cursor is at `[1149, 384, 1163, 387]`; showing its cropped source layer reconstructs its source pixels exactly, and hiding it leaves no permanent underscore.
- The cursor repair is confined to a `25×16 px` local patch. All pixels outside the patch remain pixel-identical to the original.
- The button glow mask covers top/right/bottom/left edges: `{'top': 3354, 'right': 672, 'bottom': 3383, 'left': 672}`. All four rounded-corner quadrants contain source border pixels: `{'top_left': 2228, 'top_right': 2397, 'bottom_left': 2467, 'bottom_right': 2201}`.
- At 720 px preview width, even the glow trough changes 2611 button-region pixels by more than 10 channel levels (peak difference 24); the pulse peak changes 8061 pixels (peak difference 71).
- The 9-second preview contains 180 frames. Animation changes are confined to the button and terminal cursor areas.
- The button detail GIF plays one complete 3.0-second glow cycle; the cursor detail GIF shows two complete 1-second blinks.
- The SVG dimensions and aspect ratio match the source; its existing border reflection, breathing halo, and cursor blink use SMIL animations.
- New PNG assets are embedded into the Lottie JSON; no remote asset paths are required.
- The reinforced 1672×941 composition was imported into the existing LottieFiles Creator draft as a full-canvas precomposition and saved. It was not published.

## Deliverables

- `profile-banner-phase-5.2.json` — self-contained Lottie composition.
- `profile-banner-phase-5.2.svg` — self-contained animated SVG.
- `preview/profile-banner-phase-5.2.gif` — full-banner preview.
- `preview/profile-banner-phase-5.2-static.png` — source-identical static preview with animation disabled.
- `preview/portfolio-button-glow-detail.gif` — enlarged border/glow detail.
- `preview/terminal-cursor-blink-detail.gif` — enlarged cursor visible/hidden detail.
- `layers/` — localized glow, cursor source, and background-repair image layers.

## Limitation

The original underscore is raster artwork, so the background pixels beneath it do not exist separately. The tiny hidden area is reconstructed by interpolation from immediately adjacent terminal pixels; that local repair is not claimed to be a recovered original vector or exact hidden texture.
