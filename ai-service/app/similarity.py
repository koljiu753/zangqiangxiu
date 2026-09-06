import math
from pathlib import Path

from PIL import Image, ImageOps


ALGORITHM_VERSION = "interpretable-rgbhist4-gray8-v1"


def extract_feature(image_path: Path) -> list[float]:
    """Return a deterministic 128-D feature: 64-bin RGB histogram + 8x8 grayscale thumbnail."""
    with Image.open(image_path) as source:
        rgb = ImageOps.exif_transpose(source).convert("RGB")
        rgb.thumbnail((256, 256))
        pixels = list(rgb.getdata())

        histogram = [0.0] * 64
        for red, green, blue in pixels:
            index = (red // 64) * 16 + (green // 64) * 4 + (blue // 64)
            histogram[index] += 1.0
        pixel_count = max(1, len(pixels))
        histogram = [value / pixel_count for value in histogram]

        # ImageOps.fit makes spatial features comparable across aspect ratios.
        thumbnail = ImageOps.fit(rgb.convert("L"), (8, 8), method=Image.Resampling.LANCZOS)
        spatial = [value / 255.0 for value in thumbnail.getdata()]

    # Equal L2 normalization means cosine similarity remains bounded and interpretable.
    return _normalize(histogram) + _normalize(spatial)


def similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Feature dimensions do not match")
    # Each half is independently normalized: average histogram and spatial cosine similarity.
    midpoint = len(left) // 2
    histogram_score = sum(a * b for a, b in zip(left[:midpoint], right[:midpoint]))
    spatial_score = sum(a * b for a, b in zip(left[midpoint:], right[midpoint:]))
    return round(max(0.0, min(1.0, (histogram_score + spatial_score) / 2.0)), 6)


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]

