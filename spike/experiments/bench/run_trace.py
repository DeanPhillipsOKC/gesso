"""The run trace (#165, S0d): where a /paint-lesson run's wall time goes, per skill step, split into Claude, tools and
renders.

    python spike/experiments/bench/run_trace.py <lesson folder> [--transcripts DIR ...] [--transcript FILE] [--out trace.json]

It finds the Claude Code transcript that made the run by the lesson folder's name: every *.jsonl under
~/.claude/projects (subagent transcripts in <session>/subagents/ too), keeping the one whose tool calls name the folder
most often. In it:

- **Phases** are the skill's steps 0 to 8. The run reads each step's file when it starts that step
  (.claude/skills/paint-lesson/steps/<N>-*.md, by cat or Read), so the phase changes at that call; going back to a
  step counts toward that step again. Before the first step file it's step 0. A transcript that never reads a step
  file falls back to the tools it runs (fit-canvas is 0, outline 2, build-steps 5, check 7, ...).
- **Tool time** is the time between a tool call and its result, with calls that ran at once counted once.
- **Render time** is the `seconds` a render prints (render and background print a JSON line with "cached" and
  "seconds"); it's part of tool time, and taken out of it.
- **Claude time** is the rest of the phase's wall time: thinking, writing, and waiting for the model.
- The `seconds` field every tool prints is summed too (`tool_printed_s`): a tool's own work, without the process
  start-up and the shell around it.

The ledger's renders (ledger.json) give the render seconds a second time, as a check, and the lesson folder's file
times give rough marks for each step (00_canvas_frame.png for 0, 99_finish.png for 1, parts/owner.png for 2, ...),
which is all there is when no transcript is found.

The window is the whole transcript for a subagent's (a subagent that ran /paint-lesson does nothing else). For a main
session's, it runs from the last /paint-lesson start before the folder is first named to the last call that names it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchlib import read_json, write_json  # noqa: E402

PHASES = {0: "set up, photo, canvas, beginner version", 1: "reference and finish", 2: "parts and outlines",
          3: "paints", 4: "stages and steps", 5: "step pictures and aids", 6: "text", 7: "check and review",
          8: "diagrams, notes, seal"}
STEP_FILE = re.compile(r"paint-lesson/steps/(\d)-[\w-]+\.md")
TOOL = re.compile(r"tools\.py\s+([a-z][a-z0-9-]*)((?:\s+--?[\w-]+(?:\s+[^\s-][^\s]*)?)*)")
TOOL_PHASE = {"store-photo": 0, "crop": 0, "fit-canvas": 0, "busy": 0, "simplify": 1, "value-study": 1, "palette": 1,
              "grid": 2, "outline": 2, "part-colors": 2, "elements": 2, "paints": 3, "build-steps": 5,
              "background": 5, "step-aids": 5, "mix": 5, "draft-text": 6, "card-adapt": 6, "check": 7,
              "step-pairs": 7, "preview-diagrams": 8, "publish": 8}
RENDER_PHASE = {"canvas": 0, "beginner": 0, "reference": 1, "finish": 1, "background": 5}
MARKS = [("00_canvas_frame.png", 0), ("00_canvas_fit.png", 0), ("00_beginner.png", 0), ("00_reference.png", 1),
         ("99_finish.png", 1), ("parts/owner.png", 2), ("mixes.json", 5), ("aids/aids.json", 5), ("text.json", 6),
         ("review.json", 7), ("trials/review/review.json", 7), ("notes.json", 8), ("sealed.json", 8)]
SUBAGENT_TOOLS = {"Agent", "Task"}


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iso(t: dt.datetime | None) -> str | None:
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if t else None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text") if c.get("type") == "text" else c.get("content")) for c in content
                         if isinstance(c, dict))
    return ""


def load(path: Path) -> list[dict]:
    """The transcript's rows that matter, in time order: tool calls, tool results, and other user or assistant rows."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") not in ("user", "assistant") or not r.get("timestamp"):
                continue
            t = _ts(r["timestamp"])
            content = (r.get("message") or {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        rows.append({"t": t, "kind": "call", "id": b.get("id"), "name": b.get("name"),
                                     "input": json.dumps(b.get("input"), ensure_ascii=False)})
                    elif b.get("type") == "tool_result":
                        rows.append({"t": t, "kind": "result", "id": b.get("tool_use_id"),
                                     "text": _text(b.get("content"))})
                    else:
                        rows.append({"t": t, "kind": r["type"], "text": _text([b]) if b.get("type") == "text" else ""})
            else:
                rows.append({"t": t, "kind": r["type"], "text": content if isinstance(content, str) else ""})
    rows.sort(key=lambda x: x["t"])
    return rows


def find(folder: str, roots: list[Path]) -> tuple[Path | None, list[dict]]:
    """The transcript whose tool calls name the folder most often, and every candidate with its count."""
    key = folder.encode("utf-8")
    found = []
    for root in roots:
        for path in sorted(Path(root).expanduser().rglob("*.jsonl")):
            try:
                if key not in path.read_bytes():
                    continue
            except OSError:
                continue
            calls = sum(1 for r in load(path) if r["kind"] == "call" and folder in r["input"])
            found.append({"transcript": str(path), "calls_naming_it": calls})
    found.sort(key=lambda c: -c["calls_naming_it"])
    best = Path(found[0]["transcript"]) if found and found[0]["calls_naming_it"] else None
    return best, found


def _window(rows: list[dict], folder: str, subagent: bool) -> tuple[int, int]:
    named = [i for i, r in enumerate(rows) if folder in (r.get("input") or "") or folder in (r.get("text") or "")]
    if not named:
        return 0, len(rows) - 1
    if subagent:
        return 0, len(rows) - 1
    start = 0
    for i in range(named[0], -1, -1):
        r = rows[i]
        if (r["kind"] == "call" and r["name"] == "Skill" and "paint-lesson" in r["input"]) or \
                (r["kind"] == "user" and "paint-lesson" in (r.get("text") or "")):
            start = i
            break
    end = named[-1]
    if rows[end]["kind"] == "call":  # to its result
        end = next((j for j in range(end, len(rows)) if rows[j]["kind"] == "result"
                    and rows[j]["id"] == rows[end]["id"]), end)
    return start, end


def _phase_of_call(r: dict) -> int | None:
    hits = STEP_FILE.findall(r["input"])
    return int(hits[-1]) if hits else None


def _tool_phase(r: dict) -> int | None:
    best = None
    for name, args in TOOL.findall(r["input"].replace("\\n", "\n")):
        if name == "render":
            m = re.search(r"--step\s+(\w+)", args)
            p = RENDER_PHASE.get(m.group(1), 5) if m else None
        else:
            p = TOOL_PHASE.get(name)
        if p is not None:
            best = p if best is None else max(best, p)
    return best


def _printed(text: str) -> list[dict]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}") and '"seconds"' in line:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and isinstance(d.get("seconds"), (int, float)):
                out.append(d)
    return out


def _union(intervals: list[tuple[dt.datetime, dt.datetime]]) -> float:
    total, end = 0.0, None
    for a, b in sorted(intervals):
        if end is None or a > end:
            total += (b - a).total_seconds()
            end = b
        elif b > end:
            total += (b - end).total_seconds()
            end = b
    return total


def trace_rows(rows: list[dict], folder: str, subagent: bool) -> dict:
    lo, hi = _window(rows, folder, subagent)
    rows = rows[lo:hi + 1]
    start, end = rows[0]["t"], rows[-1]["t"]
    results = {r["id"]: r for r in rows if r["kind"] == "result"}
    calls = [r for r in rows if r["kind"] == "call"]
    by_files = any(_phase_of_call(c) is not None for c in calls)
    switches, phase = [(start, 0)], 0
    for c in calls:
        p = _phase_of_call(c) if by_files else _tool_phase(c)
        if p is not None and (by_files or p > phase) and p != phase:
            phase = p
            switches.append((c["t"], p))
    segments = [(t, switches[i + 1][0] if i + 1 < len(switches) else end, p) for i, (t, p) in enumerate(switches)]

    phases = {p: {"phase": p, "name": PHASES[p], "wall_s": 0.0, "claude_s": 0.0, "tool_s": 0.0, "render_s": 0.0,
                  "tool_other_s": 0.0, "tool_printed_s": 0.0, "calls": 0, "renders": 0, "by_tool_s": {},
                  "started": None} for p in PHASES}
    for a, b, p in segments:
        ph = phases[p]
        ph["started"] = ph["started"] or _iso(a)
        wall = max(0.0, (b - a).total_seconds())
        mine = [c for c in calls if a <= c["t"] < b or (b == end and c["t"] == end)]
        spans, render, printed = [], 0.0, 0.0
        for c in mine:
            res = results.get(c["id"])
            stop = min(res["t"], b) if res else c["t"]
            spans.append((c["t"], max(c["t"], stop)))
            label = "subagent" if c["name"] in SUBAGENT_TOOLS else c["name"]
            took = (stop - c["t"]).total_seconds() if res else 0.0
            ph["by_tool_s"][label] = round(ph["by_tool_s"].get(label, 0.0) + max(0.0, took), 1)
            for d in _printed(res["text"] if res else ""):
                printed += d["seconds"]
                if "cached" in d and not d.get("cached"):
                    render += d["seconds"]
                    ph["renders"] += 1
        tool = _union(spans)
        render = min(render, tool)
        ph["wall_s"] += wall
        ph["tool_s"] += tool
        ph["render_s"] += render
        ph["tool_other_s"] += tool - render
        ph["claude_s"] += max(0.0, wall - tool)
        ph["tool_printed_s"] += printed
        ph["calls"] += len(mine)
    out = []
    for p in PHASES:
        ph = phases[p]
        for k in ("wall_s", "claude_s", "tool_s", "render_s", "tool_other_s", "tool_printed_s"):
            ph[k] = round(ph[k], 1)
        out.append(ph)
    totals = {k: round(sum(ph[k] for ph in out), 1)
              for k in ("wall_s", "claude_s", "tool_s", "render_s", "tool_other_s", "tool_printed_s")}
    totals["calls"] = sum(ph["calls"] for ph in out)
    return {"window": {"start": _iso(start), "end": _iso(end), "wall_s": round((end - start).total_seconds(), 1)},
            "phases_from": "step files" if by_files else "tool names", "phases": out, "totals": totals}


def ledger_renders(lesson: Path) -> dict:
    calls = [c for c in (read_json(lesson / "ledger.json") or {}).get("calls") or [] if c.get("tool") == "render"]
    per = {}
    for c in calls:
        if c.get("cached"):
            continue
        p = RENDER_PHASE.get(c.get("step"), 5)
        per[p] = round(per.get(p, 0.0) + float(c.get("seconds") or 0.0), 1)
    return {"renders": len(calls), "seconds": round(sum(per.values()), 1), "by_phase": per,
            "cost_usd": round(sum(float(c.get("cost_usd") or 0) for c in calls), 4)}


def file_marks(lesson: Path) -> dict:
    out = {}
    for name, p in MARKS:
        f = lesson / name
        if f.exists():
            out[name] = {"phase": p, "at": _iso(dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc))}
    m = re.search(r"_skill_(\d{8}-\d{6})$", lesson.name)
    if m:
        out["folder name (local time)"] = {"phase": 0, "at": m.group(1)}
    return out


def trace(lesson: Path, roots: list[Path] | None = None, transcript: Path | None = None) -> dict:
    lesson = Path(lesson)
    folder = lesson.name
    candidates = []
    if transcript is None:
        transcript, candidates = find(folder, roots or [Path.home() / ".claude" / "projects"])
    report = {"lesson": folder, "transcript": str(transcript) if transcript else None, "candidates": candidates,
              "ledger": ledger_renders(lesson), "file_marks": file_marks(lesson), "warnings": []}
    if transcript is None:
        report["warnings"].append("no transcript names this folder: only the ledger and the file times are known")
        return report
    rows = load(Path(transcript))
    report.update(trace_rows(rows, folder, "/subagents/" in str(transcript)))
    seen, led = report["totals"]["render_s"], report["ledger"]["seconds"]
    if abs(seen - led) > max(5.0, 0.1 * led):
        report["warnings"].append(f"renders in the transcript ({seen} s) and in the ledger ({led} s) differ")
    return report


def table(report: dict) -> str:
    if "phases" not in report:
        return f"{report['lesson']}: {report['warnings'][0]}"
    lines = [f"{report['lesson']}  ({Path(report['transcript']).name}, phases from {report['phases_from']})",
             f"{'step':<44}{'wall':>7}{'claude':>8}{'tools':>7}{'render':>8}{'calls':>7}"]
    for ph in report["phases"]:
        if not ph["wall_s"]:
            continue
        lines.append(f"{str(ph['phase']) + '. ' + ph['name']:<44}{ph['wall_s'] / 60:>6.1f}m{ph['claude_s'] / 60:>7.1f}m"
                     f"{ph['tool_other_s'] / 60:>6.1f}m{ph['render_s'] / 60:>7.1f}m{ph['calls']:>7}")
    t = report["totals"]
    lines.append(f"{'total':<44}{t['wall_s'] / 60:>6.1f}m{t['claude_s'] / 60:>7.1f}m{t['tool_other_s'] / 60:>6.1f}m"
                 f"{t['render_s'] / 60:>7.1f}m{t['calls']:>7}")
    lines += [f"warning: {w}" for w in report["warnings"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lesson")
    ap.add_argument("--transcripts", action="append", help="folders to search (default ~/.claude/projects)")
    ap.add_argument("--transcript", help="the transcript to read, instead of searching")
    ap.add_argument("--out", help="write the trace JSON here")
    a = ap.parse_args(argv)
    report = trace(Path(a.lesson), [Path(x) for x in a.transcripts] if a.transcripts else None,
                   Path(a.transcript) if a.transcript else None)
    if a.out:
        write_json(Path(a.out), report)
    print(table(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
