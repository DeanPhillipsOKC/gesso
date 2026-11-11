"""Contact sheet of every filter (#7): one row per photo, the photo first, then each filter at its defaults.

    python spike/filter_sheet.py photos/backlit-trees.jpg photos/sleeping-cat.jpg
    python spike/filter_sheet.py photos/*            # every photo

Writes output/filters/sheet.png. Local only, like the photos.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

import filters as f  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILE = 360


def tiles_for(path: Path) -> list[tuple[str, np.ndarray]]:
    rgb = f.load(path, 1024)
    sw = f.palette(rgb)
    strip = f.swatch_image(sw, rgb.shape[1], max(1, rgb.shape[0] // 4))
    pal = np.vstack([f.posterize(rgb, palette_rgb=[s["rgb"] for s in sw]), strip])
    return [
        ("photo", rgb),
        ("value-study 3", f.value_study(rgb, 3)),
        ("value-study 5", f.value_study(rgb, 5)),
        ("notan", f.notan(rgb)[0]),
        ("squint", f.squint(rgb)),
        ("palette (posterized to it)", pal),
        ("simplify kuwahara", f.simplify(rgb)),
        ("simplify meanshift", f.simplify(rgb, method="meanshift")),
        ("posterize 6", f.posterize(rgb)),
        ("edges", f.edges(rgb)),
        ("grid", f.grid(rgb)),
    ]


def fit(rgb: np.ndarray) -> Image.Image:
    img = Image.fromarray(rgb)
    img.thumbnail((TILE, TILE))
    tile = Image.new("RGB", (TILE, TILE), (245, 245, 245))
    tile.paste(img, ((TILE - img.width) // 2, (TILE - img.height) // 2))
    return tile


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "filters" / "sheet.png")
    a = ap.parse_args()

    rows = [tiles_for(p) for p in a.photos]
    label_h = 26
    cols = len(rows[0])
    sheet = Image.new("RGB", (cols * TILE, len(rows) * (TILE + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    for r, row in enumerate(rows):
        y = r * (TILE + label_h)
        for c, (label, img) in enumerate(row):
            draw.text((c * TILE + 6, y + 6), f"{a.photos[r].stem}: {label}" if c == 0 else label, fill=(20, 20, 20))
            sheet.paste(fit(img), (c * TILE, y + label_h))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
