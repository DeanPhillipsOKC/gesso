"""Where a lesson came from: made hands-off by the skill, recut from another run, or edited after the skill finished.

    seal(lesson, data) -> sealed.json: the lesson exactly as the skill finished it (publish --final, the skill's last step)
    of(lesson, data) -> {"kind": "hands-off" | "recut" | "edited" | "unsealed", ...}
    mark(lesson, kind, note) -> provenance.json, for runs from before seals (classified by hand, with a reason)

Owner, 2026-11-12: "Ideally the site would only contain lessons legitimately created by the tool and not corrected
by tweaks. Once we move from POC to app, we won't have the ability to make tweaks and adjustments like that, so the
tool really should be able to stand on its own." The skill's own fixes (its text review, a step split in the plan) count
as the tool. Anything done to a lesson after the skill seals it, a recut, a hand composite, text trimmed in a
conversation, doesn't. Only hands-off lessons go on the lessons site; everything stays in the lesson history.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

KINDS = ("hands-off", "recut", "edited", "unsealed")


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def seal(lesson: Path, data: dict) -> dict:
    from history import digest
    if (lesson / "derived.json").exists():
        raise ValueError("a recut can't be sealed as hands-off: it was made from another run")
    old = _read(lesson / "sealed.json")
    if old:
        return old  # sealed once, when the skill finished; a later --final doesn't move it
    s = {"at": dt.datetime.now().isoformat(timespec="seconds"), "digest": digest(lesson, data),
         "version": (data.get("gesso") or {}).get("version", "")}
    (lesson / "sealed.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def of(lesson: Path, data: dict) -> dict:
    from history import digest
    derived = _read(lesson / "derived.json")
    if derived:
        return {"kind": "recut", "from": derived.get("from", ""), "note": derived.get("note", "")}
    sealed = _read(lesson / "sealed.json")
    if sealed:
        if sealed["digest"] == digest(lesson, data):
            return {"kind": "hands-off", "sealed": sealed["at"]}
        return {"kind": "edited", "sealed": sealed["at"], "note": "changed after the skill finished"}
    marked = _read(lesson / "provenance.json")
    if marked:
        return marked
    return {"kind": "unsealed", "note": "not finished by the skill, or from before seals"}


def mark(lesson: Path, kind: str, note: str) -> dict:
    if kind not in ("hands-off", "edited"):
        raise ValueError("mark a run hands-off or edited")
    if not note.strip():
        raise ValueError("say why: what you know about how this run was made")
    p = {"kind": kind, "note": note, "marked": dt.date.today().isoformat()}
    (lesson / "provenance.json").write_text(json.dumps(p, indent=2), encoding="utf-8")
    data_path = lesson / "lesson.json"
    if data_path.exists():  # update the published record without republishing
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["provenance"] = of(lesson, data)
        data_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def derive(dst: Path, src: Path, note: str) -> None:
    """A copy made from another run: never hands-off, whatever happens to it later."""
    for name in ("sealed.json", "provenance.json"):
        (dst / name).unlink(missing_ok=True)
    (dst / "derived.json").write_text(json.dumps({"from": src.name, "note": note,
                                                  "at": dt.datetime.now().isoformat(timespec="seconds")}, indent=2),
                                      encoding="utf-8")
