"""Source pictures, kept in the repo so any session can rerun a lesson (#147).

    photos/<photo stem>.<ext>     one file per picture, tracked in git, named by the stem the runs use
                                  (output/<photo stem>_skill_<run time>/), e.g. photos/chickadee.jpg
    photos/private/               ignored by git: pictures that must never go in the repo

Only AI-made pictures, or ones the owner has the rights to, go in photos/ (docs/decisions.md, "Photos stay
private"). The lessons site is built from site/ alone, so nothing in photos/ is ever deployed.

    store(photo)                  -> copies a picture into photos/ at the start of a run, unless it's there
    stored(stem)                  -> photos/<stem>.<ext>, or None
    committed(path)               -> whether git tracks it (None outside a git checkout)
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "photos"
PRIVATE = "private"  # photos/private/ is ignored by git
EXTS = (".jpg", ".jpeg", ".png", ".webp")

PERSONAL = ("Only AI-made pictures or ones the owner has the rights to go in the repo. Never commit a personal photo "
            "(people, homes, anything private): if this is one, delete {path} and keep the photo in photos/private/ "
            "or outside the repo; its lesson can't go on the site.")


def stored(stem: str, photos: Path = PHOTOS) -> Path | None:
    """The stored picture for a photo stem (photos/<stem>.jpg, .png, ...), or None."""
    for ext in EXTS:
        for p in (photos / f"{stem}{ext}", photos / f"{stem}{ext.upper()}"):
            if p.is_file():
                return p
    return None


def committed(path: Path) -> bool | None:
    """Whether git tracks the file: True, False, or None when it isn't in a git checkout (or git is missing)."""
    try:
        r = subprocess.run(["git", "-C", str(path.parent), "ls-files", "--", path.name],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return bool(r.stdout.strip())


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def store(photo: Path, photos: Path | None = None) -> dict:
    """Make sure a run's picture is stored in photos/ under its stem, copying it there if it isn't. A picture in
    photos/private/ is left where it is (it never goes in the repo). Another picture already stored under the same
    stem is a problem: the runs and the site find a picture by its stem, so this one needs another name."""
    photo = Path(photo)
    if not photo.is_file():
        return {"stored": "", "copied": False, "committed": None, "problems": [f"{photo} isn't a file"]}
    if photo.suffix.lower() not in EXTS:
        return {"stored": "", "copied": False, "committed": None,
                "problems": [f"{photo.name}: keep source pictures as {', '.join(EXTS)}; convert it and run again"]}
    photos = Path(PHOTOS if photos is None else photos)
    if photo.resolve().parent == (photos / PRIVATE).resolve():
        return {"stored": "", "copied": False, "committed": None, "problems": [],
                "note": f"{photo.name} is in photos/{PRIVATE}/, which stays out of the repo, so it isn't stored. "
                        "Other sessions can't rerun this lesson, and it can't go on the site."}
    have = stored(photo.stem, photos)
    copied = False
    if have is None:
        photos.mkdir(parents=True, exist_ok=True)
        have = photos / f"{photo.stem}{photo.suffix.lower()}"
        shutil.copyfile(photo, have)
        copied = True
    elif have.resolve() != photo.resolve() and not filecmp.cmp(have, photo, shallow=False):
        return {"stored": rel(have), "copied": False, "committed": committed(have),
                "problems": [f"{rel(have)} is a different picture with the same name. Runs and the site find a "
                             f"picture by its name, so give {photo.name} a new one and run again"]}
    is_committed = committed(have)
    out = {"stored": rel(have), "copied": copied, "committed": is_committed, "problems": []}
    if not is_committed:
        out["next"] = (f"Commit {rel(have)} with the run (git add {rel(have)}), so any session can rerun this "
                       "lesson from a fresh clone. " + PERSONAL.format(path=rel(have)))
    return out
