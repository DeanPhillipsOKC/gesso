"""Tile a lesson's images into one picture: python spike/contact_sheet.py output/<lesson-folder>"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

folder = Path(sys.argv[1])
paths = [p for p in sorted(folder.glob("*.png")) if p.name != "contact_sheet.png"]
thumbs = []
for p in paths:
    im = Image.open(p).convert("RGB")
    im.thumbnail((480, 480))
    thumbs.append((p.stem, im))
w = max(t.width for _, t in thumbs)
h = max(t.height for _, t in thumbs) + 24
cols = 4
rows = -(-len(thumbs) // cols)
sheet = Image.new("RGB", (cols * w, rows * h), "white")
draw = ImageDraw.Draw(sheet)
for i, (name, t) in enumerate(thumbs):
    x, y = (i % cols) * w, (i // cols) * h
    sheet.paste(t, (x, y + 24))
    draw.text((x + 6, y + 6), name, fill="black")
out = folder / "contact_sheet.png"
sheet.save(out)
print(out)
