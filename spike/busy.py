"""How busy a picture is: the share of it that is fine texture, for the beginner-sized check (#109).

    measure(rgb) -> {"fine_texture": share of 40 px tiles that are dense with edges, "edges": share of edge pixels}
    run(picture, lesson) -> the numbers, the picture of where the texture is, and the comparison with the photo

From the spike for #52 (`docs/spikes/tools-before-plan.md`, section 1): fine texture is 10.3% on the fitted lavender
photo, 0.4% on the chickadee, 0.0% on the sailboat, and 0.0 to 0.2% on the five rendered beginner versions. It finds
textures made of hundreds of items (stalks); it doesn't see tiny separate things (a village) or count parts.

It's an aid Claude reads at step 0c, not a judge: three pictures can't set a threshold, so nothing here decides
whether a picture is too busy or blocks a run. The one comparison it makes is with the photo's own number, once a
beginner version was made: its fine texture, and the finish's, should come down.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

import filters

WORK = 1000  # every measure is taken at this long side, so pictures of different sizes compare
TILE = 40  # pixels at WORK size: a tile is fine texture when more than DENSE of its pixels are on an edge
DENSE = 0.125
SAME_SHAPE = 0.02  # a picture within 2% of the frame's shape is in the frame, so canvas_box applies to it
FADE = 0.55  # how far the rest of the picture is faded toward white in the picture of where the texture is
MARK = (224, 17, 157)  # the tiles' outline, a magenta no painting here uses

ROLES = ("photo", "beginner", "finish")
# The lesson's own files. Any other picture (a redo in trials/, the photo before fit-canvas) needs --as, so its
# number never lands on the wrong role and replaces the photo's without a word (review of #138).
ROLE_OF = {"00_canvas_frame.png": "photo", "00_canvas_fit.png": "photo", "00_beginner.png": "beginner",
           "99_finish.png": "finish"}


def edges(rgb: np.ndarray) -> np.ndarray:
    """Where the edges are (Canny, after a light blur so a canvas weave or JPEG noise doesn't count)."""
    gray = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (0, 0), 1.5)
    return cv2.Canny(gray, 40, 120) > 0


def tiles(edge: np.ndarray) -> np.ndarray:
    """Which TILE-pixel tiles are fine texture: one True per tile (rows, columns). A part tile at the right and
    bottom edges isn't measured."""
    h, w = edge.shape
    t = TILE
    share = edge[:h // t * t, :w // t * t].reshape(h // t, t, w // t, t).mean(axis=(1, 3))
    return share > DENSE


def measure(rgb: np.ndarray) -> dict:
    """The numbers for a picture already at WORK size."""
    edge = edges(rgb)
    dense = tiles(edge)
    return {"fine_texture": round(float(dense.mean()) if dense.size else 0.0, 3),
            "edges": round(float(edge.mean()), 4), "tiles": int(dense.sum())}


def picture(rgb: np.ndarray) -> np.ndarray:
    """The picture faded toward white, with each fine-texture tile at full color and outlined."""
    dense = tiles(edges(rgb))
    out = (rgb.astype(np.float32) * (1 - FADE) + 255 * FADE).astype(np.uint8)
    t = TILE
    for r, c in zip(*np.nonzero(dense)):
        y0, x0 = r * t, c * t
        out[y0:y0 + t, x0:x0 + t] = rgb[y0:y0 + t, x0:x0 + t]
    for r, c in zip(*np.nonzero(dense)):
        y0, x0 = int(r * t), int(c * t)
        cv2.rectangle(out, (x0, y0), (x0 + t - 1, y0 + t - 1), MARK, 2)
    return out


def to_work(rgb: np.ndarray) -> np.ndarray:
    s = WORK / max(rgb.shape[:2])
    return cv2.resize(rgb, (round(rgb.shape[1] * s), round(rgb.shape[0] * s)), interpolation=cv2.INTER_AREA)


def canvas_part(rgb: np.ndarray, lesson: Path) -> tuple[np.ndarray, str]:
    """The part of the picture that's on the painter's canvas. A lesson's pictures (the fitted photo, the beginner
    version, the finish) are in the image model's frame, with the canvas inside it (`canvas.json`'s canvas_box);
    a picture that isn't the frame's shape (a photo before fit-canvas) is measured whole."""
    path = lesson / "canvas.json"
    if not path.exists():
        return rgb, "the whole picture (no canvas.json yet)"
    info = json.loads(path.read_text(encoding="utf-8"))
    box, frame = info.get("canvas_box"), info.get("frame_size")
    h, w = rgb.shape[:2]
    if not box or list(box) == [0, 0, 1, 1]:
        return rgb, "the canvas (the whole picture)"
    if frame and abs((w / h) / (frame[0] / frame[1]) - 1) > SAME_SHAPE:
        return rgb, "the whole picture (it isn't the canvas frame's shape)"
    x0, y0, x1, y1 = box
    return rgb[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)], "the canvas"


def role_of(path: Path) -> str:
    """The role a picture's name gives it. Raises ValueError for any other name."""
    if path.name not in ROLE_OF:
        raise ValueError(f"{path.name} isn't the fitted photo (00_canvas_frame.png or 00_canvas_fit.png), "
                         "00_beginner.png, or 99_finish.png: say which it stands for with --as photo|beginner|finish")
    return ROLE_OF[path.name]


def _notes(lesson: Path) -> dict:
    path = lesson / "notes.json"
    if not path.exists():
        return {}
    try:
        notes = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"notes.json isn't valid JSON ({e}); fix it and run busy again") from e
    if not isinstance(notes, dict):
        raise ValueError("notes.json isn't a JSON object (steps/notes.md has its shape); fix it and run busy again")
    return notes


def record(lesson: Path, role: str, numbers: dict) -> dict:
    """Put the numbers in notes.json's beginner_version.busy[role], keeping everything else in the notes. Read
    fresh every time: Claude writes notes.json between tool runs."""
    notes = _notes(lesson)
    bv = notes.get("beginner_version")
    if not isinstance(bv, dict):  # a sentence or a list stands for the list of changes, as the page reads it
        bv = {"list": bv} if bv else {}
    busy = bv.get("busy") if isinstance(bv.get("busy"), dict) else {}
    busy[role] = numbers
    bv["busy"] = {r: busy[r] for r in ROLES if r in busy}
    notes["beginner_version"] = bv
    (lesson / "notes.json").write_text(json.dumps(notes, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return bv["busy"]


def run(path: Path, lesson: Path, role: str | None = None) -> dict:
    """Measure one picture of a lesson, write where its texture is to busy/<name>.jpg, and record the numbers."""
    if not role and path.resolve().parent != lesson.resolve():
        raise ValueError(f"{path} isn't in the lesson folder itself, so its name doesn't say what it is (a trial copy?): "
                         "measure the lesson's own file, or say which it stands for with --as photo|beginner|finish")
    role = role or role_of(path)
    rgb, measured = canvas_part(filters.load(path), lesson)
    rgb = to_work(rgb)
    numbers = measure(rgb)
    out = lesson / "busy" / (path.stem + ".jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(picture(rgb), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    entry = {"picture": path.name, **numbers, "where": str(out.relative_to(lesson)).replace("\\", "/")}
    recorded = record(lesson, role, entry)
    result = {"role": role, "measured": measured, **numbers, "picture": str(out), "recorded": recorded}
    photo = recorded.get("photo")
    if role == "photo":
        result["advice"] = ("Read the picture: the outlined tiles are fine texture (hundreds of small items). Use the "
                            "number and where the tiles are when you answer the four questions, and name those places in "
                            "the drop and merge list. It doesn't see tiny separate things (houses, posts) or count "
                            "parts: answer those by looking. It's not a threshold: you decide.")
    elif not photo:
        result["advice"] = ("There's no photo number to compare with: run busy on the photo (the fitted one, "
                            "00_canvas_frame.png or 00_canvas_fit.png) too.")
    elif role == "finish" and not (lesson / "00_beginner.png").exists():
        # A calm picture's finish measures a little more than its photo, from brush marks (chickadee 0.4% to
        # 1.7%): with no beginner version there's nothing to compare.
        result["advice"] = "No beginner version was made, so there's nothing to compare: the number is only recorded."
    else:
        down = numbers["fine_texture"] < photo["fine_texture"] or numbers["fine_texture"] == 0
        result["came_down"] = down
        result["photo_fine_texture"] = photo["fine_texture"]
        what = "beginner version" if role == "beginner" else "finish"
        result["advice"] = (f"Fine texture came down from the photo's ({photo['fine_texture']:.1%} to "
                            f"{numbers['fine_texture']:.1%}). Still Read the picture: nothing on your drop list should "
                            "be outlined." if down else
                            f"Fine texture didn't come down ({photo['fine_texture']:.1%} in the photo, "
                            f"{numbers['fine_texture']:.1%} in the {what}). Read the picture to see where it's left, and "
                            "use your one redo with those places named in the prompt.")
    return result
