# Phase 3 animation proof of concept

## Deliverables

- `profile-banner-animated.svg` — animated, self-contained SVG. The base PNG is embedded; the three derived glow PNGs are embedded in the SVG.
- `profile-banner-animation-preview.png` — representative frame at 1672 × 941.
- `profile-banner-animation-preview.gif` — 18 changing frames at 1672 × 941, 500 ms per frame, looping for 9 seconds.
- `profile-banner-animated.json` and `lottie/images/` — a companion Lottie-Web export and its four image assets.
- `lottie-preview.html` — local browser preview for the Lottie export.
- `generate_phase3.py` — reproducible asset generator; it reads the Phase 2 inputs and only writes to this Phase 3 directory.
- `source-hashes.json` — SHA-256 fingerprints recorded for the protected source files and confirmed unchanged after generation.

## Existing regions used

All three overlays were read from `assets/phase-2-layered/layers/` at 1672 × 941. They are existing raster selections from the original artwork, not editable vector paths.

| SVG/Lottie layer | Existing selected feature | Effect footprint (x, y, width, height) | Treatment |
|---|---|---:|---|
| `circuit-light-overlay` | Two short blue/violet accent strokes at the far left | 0, 198, 118, 35 | A blue-to-cyan tint and restrained glow derived from the selection alpha; smooth 9-second intensity pulse. |
| `button-highlight-overlay` | Straight middle section of the button's top border only | 1110, 449, 470, 4 | A narrow cool highlight derived from those border pixels; gently pulsed. Corners, sides, and the rest of the border are not animated. |
| `ambient-light-overlay` | Existing decorative dots in the upper-left field | 10, 10, 170, 108 | A diffuse blue-violet glow derived from the dot selection; softly pulsed out of phase with the other effects. |

The PNG glow layers contain alpha only inside the listed local regions. Their color and blur are derived from the Phase 2 selection masks; they do not add paths, dots, or other artwork. The original image is the bottom layer and remains static. The representative PNG and GIF composite the same effects over the unchanged base.

## Fidelity and unresolved areas

- The base remains 1672 × 941 and keeps the original aspect ratio. Its pixels match `assets/image.png`; the Phase 2 static preview also matches the source pixel-for-pixel.
- No Phase 1, Phase 2, original source, or pre-existing `assets/profile-banner-animated.svg` file was edited. See `source-hashes.json` for the verified hashes.
- No text, icons, terminal, or full-banner geometry was recreated or animated.
- The terminal cursor remains baked into the base, so it cannot blink without changing or covering original pixels.
- The remaining circuit paths and the button corners and side borders remain part of the static base. They are not separate editable layers.

## Validation

- Rendered the working SVG and Lottie export in the local Chromium browser at their 1672 × 941 composition size. The SVG overlay-group opacities changed between browser samples; Lottie-Web loaded all four PNG assets and its overlay opacities changed between samples. The Lottie preview reported 270 frames at 30 fps, with no browser console errors.
- The SVG uses SMIL opacity animation. The Lottie export uses ordinary image layers with animated opacity and alpha-transparent PNG glow assets; it avoids SVG filter features that Lottie does not reproduce. The Lottie result is therefore a close raster-overlay equivalent, not a conversion of the SVG animation instructions.
- Generated 18 GIF frames, confirmed the preview contains multiple frames, and checked that the effect calculation at 0 and 9 seconds is identical. The SVG and Lottie opacity curves are smooth and periodic over the same 9-second loop.
- Checked all generated glow alpha bounds against their intended regions. The transparent areas remain clear, and no effect extends to text or unrelated composition regions.
- `npm run build` completed successfully. Vite reports a non-fatal direct-`eval` warning from the installed upstream `lottie-web` player bundle.

## Lottie-Web setup

The project already has `lottie-web` 5.13.x installed and wired into its Vite app. This phase adds a tested companion Lottie JSON and a preview page without replacing the existing app demo. To preview it while the Vite server is running, open `assets/phase-3-animation/lottie-preview.html`.
