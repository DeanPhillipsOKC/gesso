"""Which Gesso made a lesson: the version in spike/VERSION, the git commit, and whether the tree had uncommitted
changes. publish stamps it on every lesson (footer, receipt, lesson.json, embed). docs/changelog.md says what
each version added."""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def version() -> str:
    return (HERE / "VERSION").read_text(encoding="utf-8").strip()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def stamp(today: dt.date | None = None) -> dict:
    commit = _git("rev-parse", "--short", "HEAD") or "unknown"
    # only code that shapes a lesson counts; site/ and docs/ edits don't make a lesson's stamp dirty
    # pathspecs from the repo root (":/"): _git runs in spike/, where plain "spike" matched nothing and the flag
    # never fired (found 2026-11-12)
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no", "--", ":/spike", ":/techniques", ":/palettes",
                      ":/.claude"))
    return {"version": version(), "commit": commit, "dirty": dirty,
            "published": (today or dt.date.today()).isoformat()}


def line(s: dict) -> str:
    """'Gesso POC 0.9.0 (a8f52bf) on 2026-11-11', with '+dirty' when made from uncommitted code."""
    return f"Gesso {s['version']} ({s['commit']}{'+dirty' if s.get('dirty') else ''}) on {s['published']}"


def with_made(current: dict, previous: dict | None) -> dict:
    """The stamp for this publish, carrying the version the lesson was first made with. Republishing a lesson with
    newer code (a relock, a site export) must not relabel what made it (site tiles, 2026-11-11: three lessons made
    with 0.17, 0.20, and 0.21 all said 0.21 after a republish)."""
    made = (previous or {}).get("made") or (
        {k: previous[k] for k in ("version", "commit", "published") if k in previous} if previous else None)
    return {**current, "made": made or {k: current[k] for k in ("version", "commit", "published")}}


def made_line(s: dict) -> str:
    """'Gesso POC 0.20.0 (7486118) on 2026-11-11', plus 'republished with POC 0.23.0' when that differs."""
    made = s.get("made") or s
    text = f"Gesso {made['version']} ({made['commit']}) on {made['published']}"
    if made.get("version") != s.get("version"):
        text += f", republished with {s['version']}"
    return text
