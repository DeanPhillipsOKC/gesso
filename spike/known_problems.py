"""A "Known problems" section on each lesson page: what the run left wrong, and the issues filed about it.

    left(data) -> problems the skill's reviews found and left as they are (lesson.json review_issues and text_issues)
    filed(run) -> GitHub issues whose text names the run's folder, open or closed (empty if gh isn't available)
    inject(html, section) -> the page with its known-problems section put in or replaced

Owner, 2026-11-12: "If a run produces bugs can you add a bugs section to each lesson with a link to an open issue
if there is one." A painter should know before they start that the water step shows patches the tool put there,
and the owner should see which issue tracks it. The section sits between markers, so it can be refreshed as issues
are filed and closed without touching the lesson itself (its pictures and text, so a hands-off lesson stays
hands-off).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import escape as e
from pathlib import Path

REPO = "DeanPhillipsOKC/gesso"
START, END = "<!--known-problems-->", "<!--/known-problems-->"
GH_PATHS = [r"C:\Program Files\GitHub CLI\gh.exe", "/c/Program Files/GitHub CLI/gh.exe"]


SAME_CONTEXT = "The text review was done by the same session that wrote the text, not a fresh one."


def left(data: dict) -> list[dict]:
    """[{"step": n, "name": ..., "problem": ...}] for each problem a review found and the run left as it is. For a
    version 2 lesson whose review.json says "review_context": "same" (the skill couldn't start a fresh reviewer),
    that too: a review by the writer misses what the writer takes for granted."""
    index = {s["id"]: (i + 1, s.get("name", s["id"])) for i, s in enumerate(data.get("stages") or [])}
    out = []
    if data.get("plan_version") == 2 and data.get("review_context") == "same":
        out.append({"step": None, "name": "", "problem": SAME_CONTEXT})
    for key in ("review_issues", "text_issues"):
        for x in data.get(key) or []:
            if not isinstance(x, dict) or not str(x.get("action", "")).lower().startswith(("left", "flag")):
                continue
            n, name = index.get(x.get("step_id"), (None, x.get("step_id", "")))
            out.append({"step": n, "name": name, "problem": x.get("problem", "")})
    return sorted(out, key=lambda p: (p["step"] or 999))


def gh() -> str | None:
    found = shutil.which("gh")
    return found or next((p for p in GH_PATHS if Path(p).exists()), None)


def filed(run: str) -> list[dict] | None:
    """Issues naming this run's folder; None when GitHub can't be asked (keep whatever the page had)."""
    exe = gh()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "issue", "list", "--repo", REPO, "--state", "all", "--search", f'"{run}" in:body',
                              "--json", "number,title,state,url", "--limit", "20"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return sorted(json.loads(out.stdout or "[]"), key=lambda i: (i["state"] != "OPEN", i["number"]))


SECTION_STYLE = """<style>
.known{border:2px solid var(--warn,#b3261e);border-radius:12px;padding:1rem;display:grid;gap:.6rem}
.known h2{margin:0}.known ul{margin:0;padding-left:1.2rem;display:grid;gap:.35rem}
.known .state{font:700 .7rem/1 ui-monospace,Consolas,monospace;text-transform:uppercase;border-radius:999px;
  padding:.2rem .45rem;margin-right:.35rem;background:var(--warn,#b3261e);color:#fff}
.known .state.closed{background:#1f7a4d}.known .small{margin:0}
</style>"""


def section(problems: list[dict], issues: list[dict]) -> str:
    if not problems and not issues:
        return f"{START}{END}"
    def where(p: dict) -> str:
        return f"<b>Step {p['step']}, {e(p['name'])}:</b> " if p["step"] else ""

    items = "".join(f'<li>{where(p)}{e(p["problem"])}</li>' for p in problems)
    links = "".join(
        f'<li><span class="state{" closed" if i["state"] != "OPEN" else ""}">'
        f'{"open" if i["state"] == "OPEN" else "fixed"}</span><a href="{e(i["url"])}">#{i["number"]} {e(i["title"])}</a></li>'
        for i in issues)
    return (f'{START}{SECTION_STYLE}<section class="known" id="known-problems"><h2>Known problems</h2>'
            + (f'<p class="small">Where the pictures aren\'t quite right. Paint it the way the step says and use the '
               f'picture as a guide.</p><ul>{items}</ul>' if problems else "")
            + (f'<p class="small">Bugs filed about this lesson on GitHub. "Fixed" means a later version of '
               f'Gesso fixes it; this lesson was made before that.</p><ul>{links}</ul>' if issues else "")
            + f"</section>{END}")


def inject(html: str, block: str) -> str:
    if START in html and END in html:
        return re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, html, count=1, flags=re.S)
    for anchor in ('<footer class="made">', "</body>"):
        if anchor in html:
            i = html.rindex(anchor)
            return html[:i] + block + html[i:]
    return html + block


def refresh_page(page: Path, run_dir: Path) -> dict:
    """Put the run's known problems on a published page; leave the page alone if GitHub can't be asked."""
    data = json.loads((run_dir / "lesson.json").read_text(encoding="utf-8"))
    problems, issues = left(data), filed(run_dir.name)
    html = page.read_text(encoding="utf-8")
    if issues is None:
        if START in html:
            return {"page": str(page), "skipped": "GitHub not available"}
        issues = []
    new = inject(html, section(problems, issues))
    if new != html:
        page.write_text(new, encoding="utf-8")
    return {"page": str(page), "left": len(problems), "issues": [i["number"] for i in issues],
            "issues_open": [i["number"] for i in issues if i["state"] == "OPEN"]}
