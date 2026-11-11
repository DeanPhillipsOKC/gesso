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
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return {"version": version(), "commit": commit, "dirty": dirty,
            "published": (today or dt.date.today()).isoformat()}


def line(s: dict) -> str:
    """'Gesso POC 0.9.0 (a8f52bf) on 2026-11-11', with '+dirty' when made from uncommitted code."""
    return f"Gesso {s['version']} ({s['commit']}{'+dirty' if s.get('dirty') else ''}) on {s['published']}"
