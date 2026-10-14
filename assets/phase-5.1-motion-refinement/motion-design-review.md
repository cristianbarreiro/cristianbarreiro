# Phase 5.1 — Motion design review

## Deliverables

- `profile-banner-phase-5.1.json`: self-contained Lottie animation, 1672 × 941, 30 fps, 9 seconds.
- `profile-banner-phase-5.1-animated.svg`: self-contained SVG with SMIL motion based on the same composition.
- `preview/profile-banner-phase-5.1-static-frame.png`: representative frame at 2.25 seconds, rendered at 1000 × 563.
- `preview/profile-banner-phase-5.1-animation-preview.gif`: 9-second animated preview at 20 fps.
- `preview/motion-contact-sheet.jpg`: five points through the loop at intended profile display size.
- `preview/lottie-player-preview.html` and `preview/svg-player-preview.html`: local player pages for the Lottie-Web and SMIL exports.

## Changes from Phase 5

- Replaced the large-ring opacity pulse with a 78° traveling highlight clipped to a source-pixel-derived ring profile. The ring remains fixed; the highlight completes one circuit per 9-second loop.
- Replaced the badge perimeter pulse with a compact 52° traveling arc completing two circuits per loop, offset from the main ring.
- Reused the existing eight comet layers for short cyan/violet light bands. Each band follows its existing circuit or button-border path, turns with the path, and fades at open endpoints so it does not pop back as a detached dot.
- Retained the original dot-field, terminal status, panel, and line-intensity layers and their staggered activity.
- Kept the Lottie layer count at 49 and the image asset count at 49; no additional effect layers were added.

## Visual review

- **Ring:** continuous arc motion around the visible circumference, with a tapered tail and no second full outline. The circle and banner remain stationary.
- **Circuit network:** a finite luminous segment follows each selected source path. Its cyan/white leading edge and violet/cyan tail read as a line sweep at 1000 × 563, rather than as a small point.
- **Button:** one band travels the existing rounded border path and eases out at the corners through tangent interpolation. Text, arrow, fill, shape, and position stay fixed.
- **CB badge:** compact edge arc stays on the source-derived perimeter and moves at a different rate from the large ring.
- **Terminal and dots:** existing staggered pulses remain secondary; the three original red, yellow, and green indicators and all text remain stationary.
- **Legibility:** all motion assets are overlays; the source image is preserved as the unchanged base. No typography, icons, button geometry, circuit paths, or dot locations were rebuilt.
- **Loop:** the 9-second loop uses periods that divide evenly into its duration. The generated opening and closing frames compare with 0 differing pixels (maximum channel difference 0) at preview size.
- **Base fidelity:** `image_base` was decoded from the Phase 5.1 JSON and compared with `assets/image.png`; the RGB pixel difference is zero. Source SHA-256: `50d22010771a31d20a9bdd051d2b0baff121fa723fb8b28f99e3c0c408821c8f`.

## Renderer and performance

The Lottie JSON was opened in the project's installed `lottie-web` player in a local browser preview; the 49-layer animation loaded and its frame counter advanced. The self-contained Animated SVG also loaded in that browser, and its SMIL clock advanced. These are actual compatible-renderer checks; the files were not imported into hosted LottieFiles Creator.

- Lottie JSON: 3,040,623 bytes; 49 image layers; 49 embedded PNG assets.
- Animated SVG: 2,626,332 bytes.
- GIF preview: 1,456,946 bytes; 180 frames, 50 ms each.
- Local generation time: 87.3 seconds.

## Limits

- The original banner is a single raster image. The effects remain pixel overlays and do not make the text, circuit geometry, or cursor independently editable.
- The ring and badge are selected from source pixels; the continuation where their circles extend beyond the canvas is inferred from neighboring visible ring pixels, then clipped by the composition bounds.
- No cursor blink is added because the cursor is embedded in the source raster and cannot be isolated without a duplicate.
- Renderer validation used local `lottie-web` 5.13.0 and browser SMIL, not the hosted LottieFiles Creator. The SVG relies on SMIL support; if a platform strips SMIL, it may display as a static frame.
