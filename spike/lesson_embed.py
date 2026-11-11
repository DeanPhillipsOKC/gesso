"""A small export of a lesson for embedding somewhere else, like a blog walkthrough.

    export(lesson_data, technique, folder) -> <folder>/embed/lesson.json plus web-sized WebP images

Each step keeps what a slide needs up front (picture, title, one-line summary, paints, brushes) and the full
instructions for a "Show instructions" toggle. Image paths in the JSON are relative to the embed folder, so it
can be copied anywhere as one folder.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from brushes import kind
from lesson_page import title_for


def summary_of(stage: dict) -> str:
    """The skill's one-line summary, or the first sentence of the first instruction, cut to about a line."""
    if stage.get("summary"):
        return stage["summary"]
    first = (stage.get("steps") or [""])[0]
    sentence = re.split(r"(?<=[.!?])\s", first, maxsplit=1)[0]
    return sentence if len(sentence) <= 120 else sentence[:117].rsplit(" ", 1)[0] + "..."


def webp(src: Path, out: Path, max_side: int) -> list[int]:
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img.thumbnail((max_side, max_side))
    img.save(out, "WEBP", quality=80, method=6)
    return list(img.size)


def export(lesson: dict, technique: dict, folder: Path) -> dict:
    out = folder / "embed"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    stages = lesson["stages"]
    first: dict[str, int] = {}
    for i, s in enumerate(stages):
        for c in s.get("colors", []):
            first.setdefault(c["name"], i + 1)

    size = None
    steps = []
    for i, s in enumerate(stages):
        n = i + 1
        size = webp(folder / s["image"], out / f"{n:02d}.webp", 1200)
        webp(folder / s["image"], out / f"{n:02d}-t.webp", 240)
        blist = s.get("brush_list") or ([{"brush": s["brushes"], "use": ""}] if s.get("brushes") else [])
        steps.append({
            "n": n, "name": s["name"], "summary": summary_of(s), "image": f"{n:02d}.webp", "thumb": f"{n:02d}-t.webp",
            "paints": [{"name": c["name"], "hex": c["hex"], "recipe": c.get("recipe", ""),
                        "first_step": first.get(c["name"], n)} for c in s.get("colors", [])],
            "brushes": [{"brush": b["brush"], "kind": kind(b["brush"]), "use": b.get("use", "")} for b in blist],
            "do": s.get("steps", []), "watch_out": s.get("watch_out", []),
        })
    extra = {}
    if lesson.get("photo_file") and (folder / lesson["photo_file"]).exists():
        webp(folder / lesson["photo_file"], out / "photo.webp", 1200)
        extra["photo"] = "photo.webp"
    if (folder / "00_beginner.png").exists():
        webp(folder / "00_beginner.png", out / "beginner.webp", 1200)
        extra["beginner"] = "beginner.webp"
    data = {
        "title": title_for(lesson, folder), "subject": lesson["photo_read"]["subject"],
        "technique": technique.get("name", ""), "level": technique.get("level", "beginner"),
        "tubes": technique.get("palette", []), "size": size, **extra,
        "cost_usd": lesson.get("total_cost_usd", 0), "steps": steps,
    }
    (out / "lesson.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"folder": str(out), "files": len(list(out.iterdir())),
            "kb": round(sum(p.stat().st_size for p in out.iterdir()) / 1024)}
