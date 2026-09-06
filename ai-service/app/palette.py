from pathlib import Path

from PIL import Image


def extract_palette(image_path: Path, color_count: int = 5) -> list[dict]:
    """Extract a deterministic dominant-color palette from actual image pixels."""
    with Image.open(image_path) as source:
        image = source.convert("RGBA")
        image.thumbnail((512, 512))
        # Ignore transparent pixels; composite opaque pixels without inventing background color.
        pixels = [(r, g, b) for r, g, b, a in image.get_flattened_data() if a >= 16]
    if not pixels:
        raise ValueError("Image contains no visible pixels")

    sample = Image.new("RGB", (len(pixels), 1))
    sample.putdata(pixels)
    quantized = sample.quantize(colors=color_count, method=Image.Quantize.MEDIANCUT)
    counts = quantized.getcolors(maxcolors=color_count) or []
    palette = quantized.getpalette() or []
    total = len(pixels)
    result = []
    for count, index in sorted(counts, reverse=True):
        rgb = tuple(palette[index * 3:index * 3 + 3])
        result.append({
            "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
            "rgb": rgb,
            "ratio": round(count / total, 6),
        })
    return result
