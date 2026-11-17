"""The frozen bench (#165, S0a): 8 pictures whose skill steps 0 and 1 are fixed, so a v3 experiment starts every
picture from the same photo, canvas fit, beginner version, reference and finish render.

    python spike/experiments/bench/bench.py freeze <sealed lesson folder> [--photo P] [--force]
    python spike/experiments/bench/bench.py build <picture>|all [--into DIR] [--stamp YYYYMMDD-HHMMSS]
    python spike/experiments/bench/bench.py verify
    python spike/experiments/bench/bench.py list

**What the bench holds fixed, and what still varies.** Fixed: everything the skill makes in steps 0 and 1, from one
sealed baseline run: the photo, the canvas fit (`canvas.json`, `00_canvas_frame.png`, and `00_canvas_fit.png` when
the run extended the canvas with a render), the beginner version (`00_beginner.png`) when the run made one, the
reference, the palette and value study the run made (every top-level `00_*` file), the finish (`99_finish.png`), and the step 0 and 1 notes
(photo, canvas fit, beginner version and its busy numbers, the technique note, the finish issues). Not fixed:
everything from step 2 on. Claude's parts, outlines, paints, stages and text are planned afresh each run, and step 5's
background render (`98_background.png`, behind ghosts and patches behind objects) is a new paid render in every
experiment. So a fault in a step picture can still come from a new render, and two v2 runs from the same bench folder
can differ; how much is not measured yet (no bench-built v2 rerun has been made).

freeze copies those files byte for byte from a sealed run into pictures/<picture>/, with canvas.json made path-free,
notes0.json (the step 0 and 1 notes), review0.json (step 1's finish issues), and manifest.json: the sha256 and size of
every file, the source run, its version and commit, and the renders that made the frozen pictures.

build makes a fresh lesson folder for an experiment from them, ready for the v2 tools from step 2 (parts) on. Every
file in it is the same bytes each build, on any machine: nothing in them names the folder, a time, or an absolute
path, JSON is written with LF line ends, and frozen text files are hashed and copied with LF line ends, so a Windows
checkout that turned them into CRLF still verifies (spike/experiments/bench/.gitattributes asks git not to). Folders
are <picture>_skill_<stamp>, under spike/experiments/bench/runs/ by default: that's outside output/, so publish
doesn't record a bench lesson in site/history/ even when GESSO_HISTORY isn't set (bench.json still says to set it).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchlib import (HERE, PICTURES, PICTURES_DIR, dumps, lf_bytes, posix, read_json, sha256,  # noqa: E402
                      write_json)

PICTURE_FILES = ["00_canvas_frame.png", "00_canvas_fit.png", "00_beginner.png", "99_finish.png"]
NEEDED = ["00_canvas_frame.png", "99_finish.png", "canvas.json"]
NOTES_KEYS = ["photo_prep", "canvas_fit", "beginner_version", "technique"]
RENDER_OF = {"canvas": "00_canvas_fit.png", "beginner": "00_beginner.png", "finish": "99_finish.png",
             "reference": "00_reference.png"}
DEFAULT_INTO = HERE / "runs"
HISTORY = "spike/experiments/bench/runs/history"  # GESSO_HISTORY for a bench lesson's publish, never site/history
NOT_CARRIED = ["busy/ (the busy tool's outlined pictures; notes keep their numbers)",
               "trials/ (filter trials and the first finish before a redo)",
               "notes.json filters (they point at trials/)",
               "the run's ledger (its renders are listed in manifest.json and as frozen calls in ledger.json)"]


class Refused(Exception):
    pass


def _frozen_names(lesson: Path) -> list[str]:
    """The step 0 and 1 files a run leaves at the top of its folder: every 00_* picture and table, and the finish."""
    names = {p.name for p in lesson.glob("00_*") if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".json")}
    return sorted(names | ({"99_finish.png"} if (lesson / "99_finish.png").exists() else set()))


def _photo_of(lesson: Path, canvas: dict, given: str | None) -> Path:
    """The run's original photo: --photo, else canvas.json's input from the checkout the run was made in (the folder
    above output/), else from this checkout."""
    from benchlib import ROOT

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

    files = _frozen_names(lesson)
    for f in files:
        if f.endswith(".json"):
            (dest / f).write_bytes(lf_bytes(lesson / f))
        else:
            shutil.copyfile(lesson / f, dest / f)
    photo_name = f"photo{src_photo.suffix.lower()}"
    shutil.copyfile(src_photo, dest / photo_name)
    write_json(dest / "canvas.json", _canvas_json(canvas, src_photo.name))
    notes = read_json(lesson / "notes.json") or {}
    write_json(dest / "notes0.json", {k: notes[k] for k in NOTES_KEYS if k in notes})
    review = read_json(lesson / "review.json") or {}
    write_json(dest / "review0.json", {"finish_issues": review.get("finish_issues", [])})

    stamp = data.get("gesso") or {}
    made = stamp.get("made") or stamp
    hashed = sorted(files + [photo_name, "canvas.json", "notes0.json", "review0.json"])
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
        "files": {f: {"sha256": sha256(dest / f), "bytes": len(lf_bytes(dest / f)) if f.endswith(".json")
                      else (dest / f).stat().st_size} for f in hashed},
    }
    write_json(dest / "manifest.json", manifest)
    return {"picture": picture, "frozen": posix(dest), "files": hashed,
            "mb": round(sum(v["bytes"] for v in manifest["files"].values()) / 1e6, 2), "source": manifest["source"]}


def manifest_of(picture: str, bench: Path = PICTURES_DIR) -> dict:
    m = read_json(Path(bench) / picture / "manifest.json")
    if not m:
        raise Refused(f"{picture} isn't frozen yet (no {posix(Path(bench) / picture / 'manifest.json')})")
    return m


def verify(bench: Path = PICTURES_DIR) -> dict:
    """{picture: "ok" | "not frozen" | what's wrong}, and "problems": every frozen picture that changed, lost a file,
    or holds a file its manifest doesn't list."""
    out, problems = {}, []
    for picture in PICTURES:
        folder = Path(bench) / picture
        if not (folder / "manifest.json").exists():
            out[picture] = "not frozen"
            continue
        m = read_json(folder / "manifest.json")
        bad = [f for f, v in m["files"].items() if not (folder / f).exists() or sha256(folder / f) != v["sha256"]]
        extra = sorted(p.name for p in folder.iterdir() if p.is_file() and p.name != "manifest.json"
                       and p.name not in m["files"])
        msg = "; ".join(x for x in (f"changed or missing: {bad}" if bad else "",
                                    f"not in the manifest: {extra}" if extra else "") if x)
        out[picture] = msg or "ok"
        if msg:
            problems.append(f"{picture}: {msg}")
    out["problems"] = problems
    return out


def build(picture: str, into: Path = DEFAULT_INTO, stamp: str | None = None, bench: Path = PICTURES_DIR,
          name: str | None = None) -> Path:
    """A fresh lesson folder for an experiment from the frozen files. The same bytes every time, on any machine."""
    m = manifest_of(picture, bench)
    src = Path(bench) / picture
    bad = [f for f, v in m["files"].items() if not (src / f).exists() or sha256(src / f) != v["sha256"]]
    if bad:
        raise Refused(f"frozen files of {picture} changed since the freeze: {bad}. Restore them from git.")
    stamp = stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(into) / (name or f"{picture}_skill_{stamp}")
    if folder.exists():
        raise Refused(f"{folder} already exists: build into a new folder")
    (folder / "trials").mkdir(parents=True)
    lesson_files = [f for f in m["files"] if f.startswith(("00_", "99_"))]
    for f in lesson_files:
        if f.endswith(".json"):
            (folder / f).write_bytes(lf_bytes(src / f))
        else:
            shutil.copyfile(src / f, folder / f)
    (folder / "canvas.json").write_bytes(lf_bytes(src / "canvas.json"))
    write_json(folder / "notes.json", read_json(src / "notes0.json") or {})
    write_json(folder / "review.json", read_json(src / "review0.json") or {"finish_issues": []})
    calls = [{"tool": "frozen", "step": r["step"], "out": r["out"], "from_run": m["source"]["run"],
              "why": "frozen on the bench: copied, not rendered", "cost_usd": 0.0, "seconds": 0.0,
              "baseline": {"model": r["model"], "quality": r["quality"], "cost_usd": r["cost_usd"],
                           "seconds": r["seconds"]}}
             for r in m["renders"]]
    write_json(folder / "ledger.json", {"calls": calls, "total_cost_usd": 0.0})
    bench_rel = posix(src)
    info = {
        "picture": picture,
        "bench": bench_rel,
        "manifest_sha256": sha256(src / "manifest.json"),
        "frozen": {f: m["files"][f]["sha256"] for f in sorted(lesson_files + ["canvas.json"])},
        "baseline": m["source"],
        "plan_photo": f"{bench_rel}/{m['plan_photo']}",
        "history": HISTORY,
        "fixed": "skill steps 0 and 1: photo, canvas fit, beginner version, reference, finish, and their notes",
        "varies": "everything from step 2: parts, outlines, paints, stages, step 5's background render (a new paid "
                  "render), text and review",
        "not_carried": NOT_CARRIED,
        "next": ("The skill's steps 0 and 1 are done: start at step 2 (parts) with plan.json's \"photo\" set to "
                 "plan_photo. review.json already holds step 1's finish_issues: keep them when step 7 writes it. "
                 "Run every tool with GESSO_HISTORY=" + HISTORY + " so a publish stays out of site/history/. Don't "
                 "render the finish, the beginner version, the reference or the canvas again."),
    }
    write_json(folder / "bench.json", info)
    return folder


def folder_hashes(folder: Path) -> dict[str, str]:
    """{relative POSIX path: sha256 of its raw bytes} of every file in a folder: what a build really wrote, CRLF and
    all (benchlib.sha256 folds CRLF for frozen files; this doesn't, so a build that wrote CRLF shows)."""
    import hashlib

    folder = Path(folder)
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("freeze", help="freeze a sealed run's steps 0 and 1: photo, canvas fit, beginner, reference, finish")
    p.add_argument("lesson")
    p.add_argument("--photo", help="the run's original photo, when canvas.json's input can't be found")
    p.add_argument("--force", action="store_true", help="replace a picture that's already frozen")
    p.add_argument("--allow-unsealed", action="store_true", help="for tests only: freeze a run that wasn't sealed")
    p = sub.add_parser("build", help="make a fresh lesson folder for an experiment from the frozen files")
    p.add_argument("picture", help=f"one of {', '.join(PICTURES)}, or all")
    p.add_argument("--into", default=str(DEFAULT_INTO), help="the folder to make it in (default "
                   "spike/experiments/bench/runs/, git-ignored and outside output/)")
    p.add_argument("--stamp", help="the run time in the folder name (default now)")
    sub.add_parser("verify", help="check every frozen file against its manifest (exit 1 on any problem)")
    sub.add_parser("list", help="which pictures are frozen, and from which run")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "freeze":
            out = freeze(Path(a.lesson), a.photo, force=a.force, allow_unsealed=a.allow_unsealed)
        elif a.cmd == "build":
            names = [p for p in PICTURES if (PICTURES_DIR / p / "manifest.json").exists()] if a.picture == "all" \
                else [a.picture]
            stamp = a.stamp or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            built = [posix(build(n, Path(a.into), stamp)) for n in names]
            out = {"built": built, "env": {"GESSO_HISTORY": HISTORY}}
        elif a.cmd == "verify":
            out = verify()
            print(json.dumps(out, indent=2))
            return 1 if out["problems"] else 0
        else:
            out = {p: (lambda m: m and {"run": m["source"]["run"], "version": m["source"]["version"],
                                        "files": len(m["files"])})(read_json(PICTURES_DIR / p / "manifest.json"))
                   or "not frozen" for p in PICTURES}
    except Refused as err:
        print(json.dumps({"problems": [str(err)]}))
        return 1
    print(json.dumps({**out, "problems": []}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
