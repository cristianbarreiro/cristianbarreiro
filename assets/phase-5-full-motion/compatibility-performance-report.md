# Phase 5 — Compatibility and performance notes

- Installed player: `lottie-web 5.13.0` (project range: `^5.13.0`).
- Lottie JSON version field: `5.12.2`.
- Canvas: `1672 × 941`.
- Frame rate and length: `30 fps`, `270 frames` (9.0 s).
- Image assets: `49`; all referenced in the main JSON as inline PNG data URIs, so the animation does not depend on remote or relative paths.
- Auxiliary PNG assets: `2257.8 KiB` total.
- Lottie JSON: `3336.1 KiB`.
- Animated SVG: `2951.1 KiB`; its raster assets are embedded and it has no script or external image references.
- Preview GIF: `1903.0 KiB`, `180 frames`, `50 ms/frame`.
- The local checks verify JSON structure, embedded image data, dimensions, frame timing, SVG XML, and pixel fidelity of the static copy. The animation was not opened in a browser or in LottieFiles Creator, so playback in those interfaces remains unverified.
- `npm run build` completed successfully with Vite. Vite emitted a warning about direct `eval` in the bundled `lottie-web` player; there were no build errors.
