# Original portfolio banner foundation

## Files

- `profile-banner-foundation.svg` is a static SVG wrapper around the original `image.png` reference.
- `profile-banner-foundation-preview.png` is the PNG rendered from that SVG at the reference's native size.

## SVG structure

The SVG uses a `1672 × 941` coordinate system and has one named group, `original-artwork`, containing `embedded-source-image`. The original PNG is embedded at its native dimensions with no crop, scaling, overlay, or added effects. Since the source is a flattened raster image, it is kept intact rather than split into inaccurate vector regions.

The background, circuit details and highlights, profile name and subtitle, terminal, monogram, contact details, portfolio button, and decorative elements all remain embedded and are not independently editable yet. The SVG metadata records existing circuit light points, the terminal cursor, the button outline, and ambient highlights as candidates for future motion. No animation or keyframes are present; original text, icons, and principal geometry remain static.

## Visual validation

The SVG was rendered to PNG at `1672 × 941` and compared with `image.png`. The decoded RGBA pixel buffers are identical across the full image. No visual discrepancies were detected in composition, text, colors, gradients, icon shapes, circuit details, cropping, or alignment. The artwork remains a single embedded image, which is the remaining editability limitation.
