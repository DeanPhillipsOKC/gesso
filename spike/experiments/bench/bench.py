"""The frozen bench (#165, S0a): 8 pictures whose photo, canvas fit, beginner version and finish render are fixed, so a
v3 experiment changes one thing and a fault can't come from a new render.

    python spike/experiments/bench/bench.py freeze <sealed lesson folder> [--photo P] [--force]
    python spike/experiments/bench/bench.py build <picture>|all [--into DIR] [--stamp YYYYMMDD-HHMMSS]
    python spike/experiments/bench/bench.py verify
    python spike/experiments/bench/bench.py list

freeze copies, byte for byte, from a sealed run: the photo, 00_canvas_frame.png, 00_canvas_fit.png (when the run
extended the canvas), 00_beginner.png (when the run made one) and 99_finish.png, into pictures/<picture>/, with
canvas.json made path-free, the run's step 0 notes (photo_prep, canvas_fit, beginner_version), and manifest.json:
the sha256 and size of every file, the source run, its version and commit, and the renders that made the frozen
files (seconds and cost, for the baseline's numbers).

build makes a fresh lesson folder for an experiment from those files, ready for the v2 tools from the skill's step 2
(parts) on: the frozen pictures, canvas.json, notes.json with the step 0 notes, ledger.json with the frozen renders
listed at no cost, and bench.json (which picture, which frozen files, and the plan's "photo" to use). Every file in it
is the same bytes each build: nothing in them names the folder, a time, or an absolute path. Folder names are
<picture>_skill_<stamp>, under output/bench/ by default; set GESSO_HISTORY (bench.json says to) so a publish there
doesn't go into site/history/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchlib import PICTURES, PICTURES_DIR, ROOT, dumps, read_json, sha256, write_json  # noqa: E402

FROZEN = ["00_canvas_frame.png", "00_canvas_fit.png", "00_beginner.png", "99_finish.png"]
NEEDED = ["00_canvas_frame.png", "99_finish.png", "canvas.json"]
NOTES_KEYS = ["photo_prep", "canvas_fit", "beginner_version"]
RENDER_OF = {"canvas": "00_canvas_fit.png", "beginner": "00_beginner.png", "finish": "99_finish.png"}
DEFAULT_INTO = ROOT / "output" / "bench"
HISTORY = "output/bench/history"  # where a bench lesson's publish records itself (GESSO_HISTORY), not site/history


class Refused(Exception):
    pass


def _rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _photo_of(lesson: Path, canvas: dict, given: str | None) -> Path:
    """The run's original photo: --photo, else canvas.json's input from the checkout the run was made in (the folder
    above output/), else from this checkout."""
    if given:
        p = Path(given)
        if not p.exists():
            raise Refused(f"--photo {given} not found")
        return p
    src = canvas.get("input")
    if not src:
        raise Refused(f"{lesson}/canvas.json has no input photo: pass --photo")
    for base in (lesson.resolve().parent.parent, ROOT):
        p = Path(src) if Path(src).is_absolute() else base / src
        if p.exists():
            return p
    raise Refused(f"the run's photo {src} wasn't found next to the run or in this checkout: pass --photo")


def _plan_photo(lesson: Path, files: list[str]) -> str:
    """The frozen file the run's plan used as "the photo" (the beginner version when one was made)."""
    plan = read_json(lesson / "plan.json") or {}
    name = Path(plan.get("photo") or "").name
    if name in files:
        return name
    for f in ("00_beginner.png", "00_canvas_fit.png", "00_canvas_frame.png"):
        if f in files:
            return f
    return "00_canvas_frame.png"


def _renders(lesson: Path, files: list[str]) -> list[dict]:
    """The ledger's renders that wrote a frozen file, redos included, oldest first."""
    ledger = read_json(lesson / "ledger.json") or {}
    out = []
    for c in ledger.get("calls") or []:
        if c.get("tool") != "render":
            continue
        name = Path(c.get("out") or "").name
        if name not in files or RENDER_OF.get(c.get("step")) != name:
            continue
        out.append({"step": c.get("step"), "out": name, "model": c.get("model"), "quality": c.get("quality"),
                    "seconds": c.get("seconds", 0.0), "cost_usd": c.get("cost_usd", 0.0),
                    "cached": bool(c.get("cached"))})
    return out


def _canvas_json(canvas: dict, photo_name: str) -> dict:
    """canvas.json with the run's own paths taken out: the frame is the lesson's file, the input the stored photo."""
    out = {k: v for k, v in canvas.items() if k not in ("frame", "input")}
    out["frame"] = "00_canvas_frame.png"
    out["input"] = f"photos/{photo_name}"
    return out


def freeze(lesson: Path, photo: str | None = None, bench: Path = PICTURES_DIR, force: bool = False,
           allow_unsealed: bool = False) -> dict:
    lesson = Path(lesson)
    missing = [f for f in NEEDED if not (lesson / f).exists()]
    if missing:
        raise Refused(f"{lesson} has no {', '.join(missing)}: freeze a finished run")
    sealed = read_json(lesson / "sealed.json")
    data = read_json(lesson / "lesson.json") or {}
    if not sealed and not allow_unsealed:
        raise Refused(f"{lesson} isn't sealed (no sealed.json): the bench freezes hands-off runs only")
    kind = (data.get("provenance") or {}).get("kind")
    if kind and kind != "hands-off" and not allow_unsealed:
        raise Refused(f"{lesson} is marked {kind}, not hands-off")
    canvas = read_json(lesson / "canvas.json")
    src_photo = _photo_of(lesson, canvas, photo)
    picture = lesson.name.split("_skill_")[0] if "_skill_" in lesson.name else src_photo.stem
    dest = Path(bench) / picture
    if dest.exists():
        if not force:
            raise Refused(f"{dest} is already frozen (from {(read_json(dest / 'manifest.json') or {}).get('source', {}).get('run')}); "
                          "pass --force to replace it")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    files = [f for f in FROZEN if (lesson / f).exists()]
    for f in files:
        shutil.copyfile(lesson / f, dest / f)
    photo_name = f"photo{src_photo.suffix.lower()}"
    shutil.copyfile(src_photo, dest / photo_name)
    write_json(dest / "canvas.json", _canvas_json(canvas, src_photo.name))
    notes = read_json(lesson / "notes.json") or {}
    write_json(dest / "notes0.json", {k: notes[k] for k in NOTES_KEYS if k in notes})

    stamp = data.get("gesso") or {}
    made = stamp.get("made") or stamp
    hashed = sorted(files + [photo_name, "canvas.json", "notes0.json"])
    manifest = {
        "picture": picture,
        "photo": photo_name,
        "photo_source": f"photos/{src_photo.name}",
        "plan_photo": _plan_photo(lesson, files),
        "beginner_version": "00_beginner.png" in files,
        "canvas_render": "00_canvas_fit.png" in files,
        "source": {"run": lesson.name, "version": made.get("version") or (sealed or {}).get("version"),
                   "commit": made.get("commit"), "dirty": bool(stamp.get("dirty")),
                   "sealed_at": (sealed or {}).get("at"), "provenance": kind or ("unsealed" if not sealed else None)},
        "renders": _renders(lesson, files),
        "files": {f: {"sha256": sha256(dest / f), "bytes": (dest / f).stat().st_size} for f in hashed},
    }
    write_json(dest / "manifest.json", manifest)
    return {"picture": picture, "frozen": _rel(dest), "files": hashed,
            "mb": round(sum(v["bytes"] for v in manifest["files"].values()) / 1e6, 2), "source": manifest["source"]}


def manifest_of(picture: str, bench: Path = PICTURES_DIR) -> dict:
    m = read_json(Path(bench) / picture / "manifest.json")
    if not m:
        raise Refused(f"{picture} isn't frozen yet (no {Path(bench) / picture / 'manifest.json'})")
    return m


def verify(bench: Path = PICTURES_DIR) -> dict:
    """Every frozen file still has the hash its manifest recorded."""
    out = {}
    for picture in PICTURES:
        path = Path(bench) / picture / "manifest.json"
        if not path.exists():
            out[picture] = "not frozen"
            continue
        m = read_json(path)
        bad = [f for f, v in m["files"].items()
               if not (path.parent / f).exists() or sha256(path.parent / f) != v["sha256"]]
        out[picture] = f"changed: {bad}" if bad else "ok"
    return out


def build(picture: str, into: Path = DEFAULT_INTO, stamp: str | None = None, bench: Path = PICTURES_DIR,
          name: str | None = None) -> Path:
    """A fresh lesson folder for an experiment from the frozen files. The same bytes every time."""
    m = manifest_of(picture, bench)
    src = Path(bench) / picture
    bad = [f for f, v in m["files"].items() if sha256(src / f) != v["sha256"]]
    if bad:
        raise Refused(f"frozen files of {picture} changed since the freeze: {bad}. Restore them from git.")
    stamp = stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(into) / (name or f"{picture}_skill_{stamp}")
    if folder.exists():
        raise Refused(f"{folder} already exists: build into a new folder")
    (folder / "trials").mkdir(parents=True)
    pictures = [f for f in FROZEN if f in m["files"]]
    for f in pictures:
        shutil.copyfile(src / f, folder / f)
    shutil.copyfile(src / "canvas.json", folder / "canvas.json")
    notes = read_json(src / "notes0.json") or {}
    (folder / "notes.json").write_text(dumps(notes), encoding="utf-8")
    calls = [{"tool": "frozen", "step": r["step"], "out": r["out"], "from_run": m["source"]["run"],
              "why": "frozen on the bench: copied, not rendered", "cost_usd": 0.0, "seconds": 0.0,
              "baseline": {"model": r["model"], "quality": r["quality"], "cost_usd": r["cost_usd"],
                           "seconds": r["seconds"]}}
             for r in m["renders"]]
    (folder / "ledger.json").write_text(dumps({"calls": calls, "total_cost_usd": 0.0}), encoding="utf-8")
    bench_rel = _rel(src)
    info = {
        "picture": picture,
        "bench": bench_rel,
        "manifest_sha256": sha256(src / "manifest.json"),
        "frozen": {f: m["files"][f]["sha256"] for f in pictures + ["canvas.json"]},
        "baseline": m["source"],
        "plan_photo": f"{bench_rel}/{m['plan_photo']}",
        "history": HISTORY,
        "next": ("The skill's steps 0 and 1 are done: start at step 2 (parts) with plan.json's \"photo\" set to "
                 "plan_photo. Run every tool with GESSO_HISTORY=" + HISTORY + " so a publish stays out of "
                 "site/history/. Don't render the finish, the beginner version or the canvas again."),
    }
    (folder / "bench.json").write_text(dumps(info), encoding="utf-8")
    return folder


def folder_hashes(folder: Path) -> dict[str, str]:
    """{relative path: sha256} of every file in a folder."""
    folder = Path(folder)
    return {str(p.relative_to(folder)): sha256(p) for p in sorted(folder.rglob("*")) if p.is_file()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("freeze", help="freeze a sealed run's photo, canvas fit, beginner version and finish")
    p.add_argument("lesson")
    p.add_argument("--photo", help="the run's original photo, when canvas.json's input can't be found")
    p.add_argument("--force", action="store_true", help="replace a picture that's already frozen")
    p.add_argument("--allow-unsealed", action="store_true", help="for tests only: freeze a run that wasn't sealed")
    p = sub.add_parser("build", help="make a fresh lesson folder for an experiment from the frozen files")
    p.add_argument("picture", help=f"one of {', '.join(PICTURES)}, or all")
    p.add_argument("--into", default=str(DEFAULT_INTO), help="the folder to make it in (default output/bench/)")
    p.add_argument("--stamp", help="the run time in the folder name (default now)")
    sub.add_parser("verify", help="check every frozen file against its manifest")
    sub.add_parser("list", help="which pictures are frozen, and from which run")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "freeze":
            out = freeze(Path(a.lesson), a.photo, force=a.force, allow_unsealed=a.allow_unsealed)
        elif a.cmd == "build":
            names = [p for p in PICTURES if (PICTURES_DIR / p / "manifest.json").exists()] if a.picture == "all" \
                else [a.picture]
            stamp = a.stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            built = [_rel(build(n, Path(a.into), stamp)) for n in names]
            out = {"built": built, "env": {"GESSO_HISTORY": HISTORY}}
        elif a.cmd == "verify":
            out = verify()
        else:
            out = {p: (lambda m: m and {"run": m["source"]["run"], "version": m["source"]["version"],
                                        "files": len(m["files"])})(read_json(PICTURES_DIR / p / "manifest.json"))
                   or "not frozen" for p in PICTURES}
    except Refused as err:
        print(json.dumps({"problems": [str(err)]}))
        return 1
    print(json.dumps({**out, "problems": []} if isinstance(out, dict) else out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
