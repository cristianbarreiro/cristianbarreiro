# Phase 2 layered banner preparation

## Composition

`profile-banner-layered.svg` preserves the Phase 1 foundation as a full-size embedded PNG in `base-artwork`. Three effect layers are separate named SVG groups, each containing a transparent PNG mask made only from source-image pixels:

- `circuit-light-overlay` selects the existing blue and violet horizontal accent strokes at the left edge (source-pixel bounds: x=0–114, y=202–228).
- `button-highlight-overlay` selects the straight middle segment of the existing portfolio button's top outline (x=1110–1579, y=449–452). The rounded corners and side borders are not included.
- `ambient-light-overlay` selects the existing upper-left decorative dot field (x=18–171, y=13–115).

The overlay PNGs are in `layers/`. They retain the original pixel colors, have alpha transparency everywhere outside their selected source pixels, and are hidden at opacity zero in the SVG. These are raster selections, not vector separations. A later highlight effect would need to brighten a selected layer; simply changing its opacity would not remove the identical pixels in the immutable base.

No `terminal-cursor-overlay` was created. The cursor is visible in the reference but baked into the base pixels; blinking it would require removing or covering the base cursor, which would violate the immutable-base requirement. The remaining circuit paths, button corners and sides, and other attached accents also remain unresolved.

## Static validation

- The base embedded in the layered SVG was decoded and compared with both `assets/image.png` and the embedded image in `profile-banner-foundation.svg`; all RGBA pixels match.
- The SVG was rendered at the original `1672 × 941` dimensions. Its PNG preview is pixel-identical to the foundation because all overlay groups are hidden.
- Each overlay was checked for full-canvas alignment and alpha transparency outside its bounded source region. No clipping, redraw, scaling, or animation was applied.
- The original `assets/image.png` and `assets/profile-banner-foundation.svg` remain unchanged. This phase prepares layers only; it does not implement an animation loop.
