# Phase 4 — circuit and portfolio-button layer expansion

## Deliverables

- `profile-banner-phase-4.svg` — Phase 3 composition plus seven source-pixel highlights and seven localized halo layers. The base artwork and all effect images are embedded.
- `profile-banner-phase-4.json` and `lottie/images/` — companion Lottie-Web composition with the same 14 independently pulsing Phase 4 layers and required image assets.
- `profile-banner-phase-4-static.svg` — full composition with every Phase 3 and Phase 4 effect layer present but disabled.
- `profile-banner-phase-4-static-preview.png` — static render at 1672 × 941.
- `phase-4-static-difference.png` — pixel difference against the Phase 1 foundation preview; it is entirely black because no pixels differ.
- `profile-banner-phase-4-animation-frame.png` — representative animated frame.
- `profile-banner-phase-4-animation-preview.gif` — 18 changing frames, 500 ms per frame, looping over 9 seconds.
- `profile-banner-phase-4-readme.gif` — README-ready 1100 × 619 version with the same 18-frame loop and reduced file size.
- `layers/` — transparent source-pixel selections, in-place highlights, and soft halos derived from those selections.
- `extraction-metrics.json` — alpha bounds and selected pixel counts for every source mask.
- `protected-source-hashes.json` — SHA-256 manifest for the protected Phase 1, Phase 2, and Phase 3 source files.
- `generate_phase4.py` and `lottie-preview.html` — reproducible generator and browser preview page.

## Regions isolated

The selections retain RGB values from the original PNG. Their alpha is derived from the original colored pixels and a narrow geometry gate used only to limit selection; no replacement vectors or artwork are drawn. Antialiased edges are retained as partial alpha. The associated effect PNGs brighten only pixels within those selection mattes, so the new highlight does not extend beyond the extracted region.

| Layer | Feature selected | Alpha bounds (x, y, right, bottom) | Result |
|---|---|---:|---|
| `circuit-upper-trace` | Upper blue trace and its existing node | (1256, 35, 1566, 77) | Isolated. The source trace ends before the right edge. |
| `circuit-mid-upper-trace` | Upper-middle stepped trace and terminal dot | (1113, 96, 1341, 146) | Isolated. |
| `button-top-border` | Straight middle of top edge | (1038, 448, 1573, 454) | Isolated; combines with the corner mask to cover the full top contour. |
| `button-bottom-border` | Straight middle of bottom edge | (1038, 602, 1573, 608) | Isolated; combines with the corner mask to cover the full bottom contour. |
| `button-left-border` | Left straight side | (1009, 479, 1015, 579) | Isolated. |
| `button-right-border` | Right straight side | (1592, 479, 1598, 579) | Isolated. |
| `button-corner-regions` | Four rounded corner arcs | (1009, 448, 1598, 608) | Isolated as one transparent image with four separate arc regions. |

The existing Phase 3 left-edge accents, center top-border highlight, and ambient dots remain in the composition. Phase 3 timing and the 9-second loop are retained. Each new circuit trace, button edge, and corner highlight has its own SVG group and Lottie image layer with independently adjustable opacity.

## Visible effect update

The first Phase 4 preview used low opacity and the highlights were too difficult to see at normal viewing size. This revision increases the pulse range, strengthens the selected-pixel highlight, and adds a soft cyan/blue halo made only from blur applied to each existing source-pixel matte. Halo radius is 2.2 px for the circuit selections and 1.8 px for the button edge selections. The halo is transparent elsewhere; no text, icon, button fill, or missing circuit segment is reconstructed. Pulse timing remains slow and staggered over the same 9-second loop. The representative PNG is sampled at 4.5 seconds to show the effect near a visible pulse.

The editable elements are independent raster effect layers (source selection, brightened core, and derived halo), not recovered vector paths. The base layer stays unchanged beneath them.

The local profile `README.md` now links the banner to `https://cristianbarreiro.github.io` and displays the README-ready GIF. The prior profile source still pointed to the Phase 3 SVG; GitHub does not animate SVG images in repository pages, so that version appeared static there. The GIF is used for the README, while SVG and Lottie deliverables remain available separately.

## Limits

- Other visible circuit traces remain static. Several intersect or disappear under the large ring, terminal panel, text, or dot field; those regions could not be separated with confidence from this flattened PNG. No paths were invented to bridge obscured portions.
- The terminal cursor remains part of the base artwork and was not extracted.
- Button text, fill, dimensions, arrow, and radius remain in the unchanged base. The edge selections are raster masks, not editable vector outlines.
- Only the two stated circuit traces and the button border have Phase 4 effects. All other circuit lines, ambient points, terminal details, and the cursor remain unmodified by Phase 4.

## Validation

- Compared the rendered Phase 4 static SVG, with every effect disabled, against both `assets/image.png` and `assets/profile-banner-foundation-preview.png` at 1672 × 941. Both comparisons were pixel-identical: zero changed pixels. The difference image records that result.
- Re-rendered the updated static SVG at 1672 × 941 and compared it directly with the original PNG: pixel-identical, zero changed pixels. Halo images remain fully transparent in the static composition.
- Confirmed the regenerated GIF has 18 frames, each 500 ms, and all 18 frame-to-frame transitions (including the loop) change pixels. The representative animated frame changes 34,453 pixels, concentrated around the selected traces and border rather than the whole banner.
- Encoded both GIFs with a shared palette and clean frame disposal to keep the pulse consistent between frames. The README version is 1100 × 619 and approximately 4.3 MB.
- Confirmed all source and prior-phase hashes still match the manifest; no Phase 1, Phase 2, Phase 3, or original banner file was modified.
- Inspected enlarged selection composites: the circuit mattes follow only the two selected source traces, while button mattes remain on the border and corner pixels, away from text and arrow. New highlight alpha bounds match their corresponding source masks.
- Rendered `profile-banner-phase-4.svg` in Chromium. Its original Phase 3 groups and all 14 Phase 4 groups are present; the groups animate their opacity over the 9-second loop.
- Loaded the companion JSON through the installed `lottie-web` SVG renderer in the project preview page. It reports 270 frames at 30 fps and “Lottie loaded”; the base and effect image assets render through the same composition.
- The Lottie version uses transparent raster image layers and animated opacity, not SVG animation tags. It preserves the appearance and timing closely while keeping all newly prepared regions independently controllable.
