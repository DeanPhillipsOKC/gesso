"""Shared helpers for the v3 yardstick (#165): paths, the bench's pictures, hashes, and reading a lesson folder.

Every tool in spike/experiments/bench/ imports this. Nothing here changes a lesson folder.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
SPIKE = ROOT / "spike"
PICTURES_DIR = HERE / "pictures"
SCORES_DIR = HERE / "scores"

# The 8 bench pictures, by photo stem (photos/<stem>.<ext>): the five on the site, then the three picked to be hard
# (docs/design/pipeline-v3-plan.md, Wave 0).
PICTURES = ["chickadee", "red-sailboat", "balloon-lavender", "sleeping-cat", "snow-lantern", "highland-cow",
            "lake-cabin", "birch-grove"]

# Fault classes from the issue history (fault_counter.md has the definitions)
CLASSES = {"A": "step pictures", "B": "outlines", "C": "placement", "D": "paints", "E": "text", "F": "teaching",
           "G": "site", "H": "tooling"}
SEVERITY = {"blocker": 3, "major": 2, "minor": 1}


TEXT = {".json", ".md", ".txt"}  # frozen text: hashed with LF line ends, whatever a checkout did to them


def sha256(path: Path) -> str:
    """A file's sha256. A text file (TEXT) is hashed as if its line ends were LF, so a Windows checkout that turned
    them into CRLF still matches the manifest written on Linux."""
    path = Path(path)
    if path.suffix.lower() in TEXT:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def lf_bytes(path: Path) -> bytes:
    """A frozen text file's bytes with LF line ends (as frozen), for copying into a build."""
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def posix(path: Path) -> str:
    """A path for a file Claude or a tool reads: forward slashes, relative to the repo when it's inside it."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def dumps(data) -> str:
    """JSON the same way every time: sorted keys, two-space indent, a newline at the end."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps(data).encode("utf-8"))  # LF on every machine (write_text gives CRLF on Windows)


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def picture_of(lesson: Path) -> str:
    """The picture a lesson folder is of: its bench.json, else the run folder's name (<stem>_skill_<time>), else the
    canvas.json input's stem."""
    lesson = Path(lesson)
    bench = read_json(lesson / "bench.json")
    if bench and bench.get("picture"):
        return bench["picture"]
    if "_skill_" in lesson.name:
        return lesson.name.split("_skill_")[0]
    canvas = read_json(lesson / "canvas.json") or {}
    if canvas.get("input"):
        return Path(canvas["input"]).stem
    return lesson.name


def picture_order(name: str) -> tuple[int, str]:
    return (PICTURES.index(name) if name in PICTURES else len(PICTURES), name)


def canvas_box(lesson: Path) -> list[float]:
    canvas = read_json(Path(lesson) / "canvas.json") or {}
    return canvas.get("canvas_box") or [0.0, 0.0, 1.0, 1.0]


def stage_image(lesson: Path, stage: dict) -> Path:
    """A published step's picture: lesson.json's `image`, which publish already cropped to the canvas (canvas/NN.png)
    when the lesson has a canvas box. Nothing is cropped here."""
    return Path(lesson) / stage["image"]


def lesson_steps(lesson: Path) -> list[dict]:
    """Every step of a published lesson (lesson.json) with what a painter is given for it: picture, words, paints,
    brushes. Only what the lesson page shows; nothing from the plan or the run's own reviews."""
    data = read_json(Path(lesson) / "lesson.json")
    if not data:
        raise FileNotFoundError(f"{lesson}/lesson.json is missing: publish the lesson first")
    groups = {}
    for g in data.get("groups") or []:
        for sid in g.get("steps") or []:
            groups[sid] = g.get("name", "")
    out = []
    for i, s in enumerate(data.get("stages") or []):
        out.append({
            "n": i + 1, "id": s.get("id", f"step-{i + 1}"), "name": s.get("name", ""),
            "group": groups.get(s.get("id"), ""), "image": stage_image(lesson, s),
            "lines": [str(x) for x in s.get("steps") or []],
            "tip": s.get("tip") or "",
            "brushes": s.get("brushes") or "",
            "paints": [{"name": c.get("name", ""), "hex": c.get("hex", ""), "recipe": c.get("recipe", "")}
                       for c in s.get("colors") or []],
        })
    return out


def crop_canvas(img, box: list[float]):
    """The canvas part of a picture in the image model's frame (the same crop publish makes)."""
    W, H = img.size
    if list(box) in ([0, 0, 1, 1], [0.0, 0.0, 1.0, 1.0]):
        return img
    return img.crop((round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H)))
