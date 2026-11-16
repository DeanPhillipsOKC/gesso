"""The blind A/B page (#165, S0b): one self-contained HTML page the owner scores on a phone, and the importer that
saves the scores next to the round on the bench.

    python spike/experiments/bench/ab_page.py make --round <name> --out page.html --lesson DIR [--lesson DIR ...]
    python spike/experiments/bench/ab_page.py make --round <name> --out page.html --pair DIR_1 DIR_2 [--pair ...] [--seed N]
    python spike/experiments/bench/ab_page.py import <scores.json> [--force]

Single mode (--lesson): one lesson per picture, for the baseline. Pair mode (--pair): two lessons of the same picture;
which one is shown as A is drawn from the seed (random.Random(f"{seed}:{picture}")), recorded in the page's answer
key and in <page>.key.json beside it. The page shows A and B only; the lesson folders are in the answer key, which is
encoded in the page and only comes back inside the copied scores.

Per lesson, 1 to 5 each: (a) the step pictures look like a real half-done painting; (b) I could paint each step from
its words; (c) the pictures, paints and words agree. Then, in pair mode, which would I paint from (A, B, no
difference); in single mode, would I paint from this (yes, maybe, no). Any step can be marked "worst step", and
every lesson and picture takes an optional note.

The page is phone-first: one picture at a time with Back and Next, one step at a time (tap the arrows or swipe the
picture), step pictures as JPEGs about 720 px on the long side. All saving goes through one JS function,
saveScores(scores): it writes localStorage today (in try/catch) and is the one place to wire a storage backend when
the page is published as an artifact. "Copy scores" copies the scores JSON (SCORES_FORMAT below) at any time.

The page is the same bytes for the same inputs and seed: nothing in it is a time or an absolute path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import random
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchlib import (SCORES_DIR, canvas_box, crop_canvas, dumps, lesson_steps, picture_of,  # noqa: E402
                      picture_order, read_json, write_json)

FORMAT = "gesso-ab-scores/1"
MAX_BYTES = 12_000_000
BUDGET = 11_500_000  # leave room under the 12 MB cap
SIDE = 720
TRIES = [(SIDE, 80), (SIDE, 72), (SIDE, 64), (SIDE, 56), (640, 56), (560, 52), (480, 50)]
RUBRIC = [
    ("real", "The step pictures look like a real half-done painting"),
    ("paintable", "I could paint each step from its words"),
    ("agree", "The pictures, paints and words agree"),
]

# The scores JSON the page copies and saveScores() receives. ab_page.py import checks it.
SCORES_FORMAT = {
    "format": FORMAT,
    "round": "the round's name (--round)",
    "mode": "single | pair",
    "seed": "the seed the sides were drawn from (pair mode; null in single mode)",
    "saved_at": "when the page last saved, ISO 8601 from the phone's clock",
    "pictures": [{
        "picture": "chickadee",
        "lessons": {"A": "<lesson folder name>", "B": "<lesson folder name, pair mode only>"},
        "scores": {"A": {"real": "1-5 or null", "paintable": "1-5 or null", "agree": "1-5 or null",
                         "would_paint": "yes | maybe | no | null (single mode only)",
                         "worst_steps": [{"n": 5, "id": "branch-dark"}], "note": ""}},
        "prefer": "A | B | same | null (pair mode only)",
        "note": "",
    }],
}


def _jpeg(img, side: int, quality: int) -> bytes:
    from PIL import Image

    img = img.convert("RGB")
    w, h = img.size
    k = side / max(w, h)
    if k < 1:
        img = img.resize((round(w * k), round(h * k)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=False)
    return buf.getvalue()


def _uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _photo(lesson: Path):
    """The photo the painter compares with: the lesson's own copy (photo.png, the plan's photo), cropped to the
    canvas; else the run's frozen photo on the bench."""
    from PIL import Image

    for name in ("photo.png", "photo.jpg"):
        if (lesson / name).exists():
            return crop_canvas(Image.open(lesson / name), canvas_box(lesson))
    for name in ("00_beginner.png", "00_canvas_fit.png", "00_canvas_frame.png"):
        if (lesson / name).exists():
            return crop_canvas(Image.open(lesson / name), canvas_box(lesson))
    return None


def _seed_for(round_name: str) -> int:
    return int(hashlib.sha256(round_name.encode("utf-8")).hexdigest()[:8], 16)


def plan_round(round_name: str, lessons: list[Path] | None = None, pairs: list[tuple[Path, Path]] | None = None,
               seed: int | None = None) -> dict:
    """Which lessons go on the page and on which side: {mode, seed, pictures: [{picture, sides: {A: path, B: path}}]}."""
    if bool(lessons) == bool(pairs):
        raise ValueError("give --lesson folders (single mode) or --pair folders (pair mode), not both")
    if lessons:
        rows = [{"picture": picture_of(p), "sides": {"A": Path(p)}} for p in lessons]
        mode, seed = "single", None
    else:
        seed = _seed_for(round_name) if seed is None else int(seed)
        rows = []
        for one, two in pairs:
            pic = picture_of(one)
            if picture_of(two) != pic:
                raise ValueError(f"a pair must be two lessons of one picture: {Path(one).name} and {Path(two).name}")
            swap = random.Random(f"{seed}:{pic}").random() < 0.5
            a, b = (two, one) if swap else (one, two)
            rows.append({"picture": pic, "sides": {"A": Path(a), "B": Path(b)}})
        mode = "pair"
    seen = [r["picture"] for r in rows]
    dup = sorted({p for p in seen if seen.count(p) > 1})
    if dup:
        raise ValueError(f"one entry per picture: {dup} came twice")
    rows.sort(key=lambda r: picture_order(r["picture"]))
    return {"round": round_name, "mode": mode, "seed": seed, "pictures": rows}


def answer_key(plan: dict) -> dict:
    return {"format": FORMAT, "round": plan["round"], "mode": plan["mode"], "seed": plan["seed"],
            "pictures": [{"picture": r["picture"], "lessons": {s: Path(p).name for s, p in r["sides"].items()}}
                         for r in plan["pictures"]]}


def _data(plan: dict, side: int, quality: int) -> dict:
    pictures = []
    for r in plan["pictures"]:
        sides = {}
        photo = None
        for s, lesson in r["sides"].items():
            lesson = Path(lesson)
            if photo is None:
                img = _photo(lesson)
                photo = _uri(_jpeg(img, side, quality)) if img is not None else ""
            from PIL import Image

            steps = []
            for st in lesson_steps(lesson):
                steps.append({"n": st["n"], "id": st["id"], "name": st["name"], "group": st["group"],
                              "img": _uri(_jpeg(Image.open(st["image"]), side, quality)),
                              "lines": st["lines"], "tip": st["tip"], "brushes": st["brushes"],
                              "paints": st["paints"]})
            sides[s] = {"steps": steps}
        pictures.append({"picture": r["picture"], "photo": photo, "sides": sides})
    return {"round": plan["round"], "mode": plan["mode"], "rubric": RUBRIC, "pictures": pictures}


def make(plan: dict, out: Path) -> dict:
    key = answer_key(plan)
    for side, quality in TRIES:
        data = _data(plan, side, quality)
        html = page(data, key)
        size = len(html.encode("utf-8"))
        if size <= BUDGET:
            break
    else:
        raise ValueError(f"the page is {size / 1e6:.1f} MB even at {side} px and quality {quality}, over "
                         f"{MAX_BYTES / 1e6:g} MB: split the round into two pages (fewer --lesson or --pair)")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    write_json(out.with_suffix(".key.json"), key)
    return {"page": str(out), "key": str(out.with_suffix(".key.json")), "mb": round(size / 1e6, 2),
            "side_px": side, "jpeg_quality": quality, "pictures": len(plan["pictures"]), "mode": plan["mode"],
            "seed": plan["seed"],
            "steps": sum(len(s["steps"]) for p in data["pictures"] for s in p["sides"].values())}


STYLE = """
:root{--bg:#f6f3ee;--fg:#1d1b19;--muted:#6b645c;--card:#fff;--line:#ddd5ca;--accent:#2f5d8a;--on:#fff;
--warn:#b3261e;--sel:#2f5d8a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#171513;--fg:#f1ece6;--muted:#a99f94;
--card:#221f1c;--line:#3a352f;--accent:#8db6e0;--on:#111;--warn:#ff8a80;--sel:#8db6e0}}
:root[data-theme="dark"]{--bg:#171513;--fg:#f1ece6;--muted:#a99f94;--card:#221f1c;--line:#3a352f;--accent:#8db6e0;
--on:#111;--warn:#ff8a80;--sel:#8db6e0}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg)}
body{font:17px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:96px;
-webkit-text-size-adjust:100%}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);
padding:10px 16px;display:flex;align-items:center;gap:8px}
header h1{font-size:17px;margin:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
header .count{color:var(--muted);font-size:15px}
main{max-width:720px;margin:0 auto;padding:0 16px}
section.pic{display:none}section.pic.on{display:block}
h2{font-size:22px;margin:18px 0 8px}h3{font-size:19px;margin:22px 0 8px}
.photo img,.viewer img{width:100%;height:auto;display:block;border-radius:10px;background:#ccc;touch-action:pan-y}
.photo{margin:0 0 8px}.photo img{width:45%}.photo.big img{width:100%}.photo figcaption,.small{color:var(--muted);font-size:14px}
.lesson{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:16px 0}
.stepbar{display:flex;align-items:center;gap:8px;margin:10px 0}
.stepbar .where{flex:1;text-align:center;font-weight:600}
button{font:inherit;color:var(--fg);background:var(--card);border:2px solid var(--line);border-radius:12px;
min-height:52px;min-width:52px;padding:8px 14px;cursor:pointer;-webkit-tap-highlight-color:transparent}
button:active{transform:scale(.98)}
button.sel,button[aria-pressed="true"]{background:var(--sel);border-color:var(--sel);color:var(--on)}
button.worst[aria-pressed="true"]{background:var(--warn);border-color:var(--warn)}
.group{color:var(--muted);font-size:14px;text-transform:uppercase;letter-spacing:.04em;margin-top:6px}
.sname{font-weight:700;font-size:19px;margin:2px 0 6px}
.paints{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 8px;padding:0;list-style:none}
.paints li{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line);border-radius:10px;
padding:6px 8px;font-size:15px;width:100%}
.sw{width:28px;height:28px;border-radius:6px;flex:none;border:1px solid rgba(0,0,0,.2)}
.paints .rec{color:var(--muted);font-size:14px;display:block}
ol.lines{padding-left:1.4em;margin:6px 0}ol.lines li{margin:4px 0}
.tip{border-left:4px solid var(--accent);padding:4px 10px;margin:8px 0}
.q{margin:14px 0}.q p{margin:0 0 6px;font-weight:600}
.scale{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.three{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.ends{display:flex;justify-content:space-between;color:var(--muted);font-size:13px;margin-top:2px}
textarea{width:100%;min-height:64px;font:inherit;border:2px solid var(--line);border-radius:12px;padding:8px;
background:var(--card);color:var(--fg)}
footer{position:fixed;left:0;right:0;bottom:0;z-index:5;background:var(--bg);border-top:1px solid var(--line);
padding:10px 16px calc(10px + env(safe-area-inset-bottom));display:grid;grid-template-columns:1fr 1.5fr 1fr;gap:8px}
footer button{width:100%;white-space:nowrap;padding:8px 6px}
#status{color:var(--muted);font-size:13px;text-align:center;min-height:1.2em;margin:6px 0}
#copybox{display:none;width:100%;min-height:160px;margin:8px 0;font:12px ui-monospace,monospace}
.done{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:16px 0}
"""

SCRIPT = r"""
(function(){
const D = JSON.parse(document.getElementById('data').textContent);
const KEY = JSON.parse(atob(document.getElementById('key').textContent.trim()));
const STORE = 'gesso-ab:' + D.round;
let at = 0;
const scores = blank();

function blank(){
  return {format: KEY.format, round: KEY.round, mode: KEY.mode, seed: KEY.seed, saved_at: null,
    pictures: KEY.pictures.map(function(p){
      const s = {};
      Object.keys(p.lessons).forEach(function(side){
        s[side] = {real: null, paintable: null, agree: null, worst_steps: [], note: ''};
        if (KEY.mode === 'single') s[side].would_paint = null;
      });
      return {picture: p.picture, lessons: p.lessons, scores: s, prefer: null, note: ''};
    })};
}

// All saving goes through here. Today: this browser's localStorage. Wire a storage backend in this one function.
function saveScores(scores){
  scores.saved_at = new Date().toISOString();
  try { localStorage.setItem(STORE, JSON.stringify(scores)); } catch (e) {}
  status('Saved on this phone. Copy scores when you finish.');
}
window.saveScores = saveScores;

function restore(){
  let old = null;
  try { old = JSON.parse(localStorage.getItem(STORE) || 'null'); } catch (e) { old = null; }
  if (!old || old.round !== scores.round || !Array.isArray(old.pictures)) return;
  old.pictures.forEach(function(op){
    const p = scores.pictures.find(function(x){ return x.picture === op.picture; });
    if (!p || JSON.stringify(p.lessons) !== JSON.stringify(op.lessons)) return;
    p.prefer = op.prefer || null; p.note = op.note || '';
    Object.keys(p.scores).forEach(function(side){ if (op.scores && op.scores[side]) Object.assign(p.scores[side], op.scores[side]); });
  });
  scores.saved_at = old.saved_at || null;
}

function status(t){ document.getElementById('status').textContent = t; }
function el(tag, attrs, kids){
  const e = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function(k){
    if (k === 'text') e.textContent = attrs[k]; else if (k === 'on') e.addEventListener('click', attrs[k]);
    else e.setAttribute(k, attrs[k]);
  });
  (kids || []).forEach(function(c){ if (c) e.appendChild(c); });
  return e;
}
function choice(values, labels, get, set, cls){
  const box = el('div', {class: cls});
  const buttons = values.map(function(v, i){
    const b = el('button', {type: 'button', text: labels[i], 'aria-pressed': String(get() === v)});
    b.addEventListener('click', function(){
      set(get() === v ? null : v);
      buttons.forEach(function(x, j){ x.setAttribute('aria-pressed', String(get() === values[j])); });
      saveScores(scores); progress();
    });
    box.appendChild(b); return b;
  });
  return box;
}

function viewer(p, side, sc){
  const steps = D.pictures[p].sides[side].steps;
  let k = 0;
  const img = el('img', {alt: 'Step picture'});
  const where = el('div', {class: 'where'});
  const worst = el('button', {type: 'button', class: 'worst', 'aria-pressed': 'false', text: 'Worst step'});
  const body = el('div');
  const prev = el('button', {type: 'button', 'aria-label': 'Previous step', text: '←'});
  const next = el('button', {type: 'button', 'aria-label': 'Next step', text: '→'});
  const where2 = el('div', {class: 'where'});
  const prev2 = el('button', {type: 'button', 'aria-label': 'Previous step', text: '←'});
  const next2 = el('button', {type: 'button', 'aria-label': 'Next step', text: '→'});
  function isWorst(){ return sc.worst_steps.some(function(w){ return w.n === steps[k].n; }); }
  function show(){
    const s = steps[k];
    img.src = s.img;
    where.textContent = where2.textContent = 'Step ' + s.n + ' of ' + steps.length;
    worst.setAttribute('aria-pressed', String(isWorst()));
    worst.textContent = isWorst() ? 'Worst step ✓' : 'Worst step';
    body.innerHTML = '';
    if (s.group) body.appendChild(el('div', {class: 'group', text: s.group}));
    body.appendChild(el('div', {class: 'sname', text: s.name}));
    if (s.paints.length){
      const ul = el('ul', {class: 'paints'});
      s.paints.forEach(function(c){
        const sw = el('span', {class: 'sw'}); sw.style.background = c.hex || '#999';
        ul.appendChild(el('li', {}, [sw, el('span', {}, [el('b', {text: c.name}), el('span', {class: 'rec', text: c.recipe})])]));
      });
      body.appendChild(ul);
    }
    if (s.brushes) body.appendChild(el('div', {class: 'small', text: 'Brush: ' + s.brushes}));
    const ol = el('ol', {class: 'lines'});
    s.lines.forEach(function(t){ ol.appendChild(el('li', {text: t})); });
    body.appendChild(ol);
    if (s.tip) body.appendChild(el('p', {class: 'tip', text: 'Tip: ' + s.tip}));
    prev.disabled = prev2.disabled = k === 0; next.disabled = next2.disabled = k === steps.length - 1;
  }
  function go(d, top){
    const n = Math.max(0, Math.min(steps.length - 1, k + d));
    if (n !== k){ k = n; show(); if (top) img.scrollIntoView({block: 'start'}); }
  }
  prev.addEventListener('click', function(){ go(-1); });
  next.addEventListener('click', function(){ go(1); });
  prev2.addEventListener('click', function(){ go(-1, true); });
  next2.addEventListener('click', function(){ go(1, true); });
  worst.addEventListener('click', function(){
    const s = steps[k];
    if (isWorst()) sc.worst_steps = sc.worst_steps.filter(function(w){ return w.n !== s.n; });
    else { sc.worst_steps.push({n: s.n, id: s.id}); sc.worst_steps.sort(function(a, b){ return a.n - b.n; }); }
    show(); saveScores(scores);
  });
  let x0 = null, y0 = null;
  img.addEventListener('touchstart', function(e){ x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, {passive: true});
  img.addEventListener('touchend', function(e){
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    x0 = null;
  });
  show();
  return el('div', {class: 'viewer'}, [img, el('div', {class: 'stepbar'}, [prev, where, next]), worst, body,
    el('div', {class: 'stepbar'}, [prev2, where2, next2])]);
}

function rubric(sc){
  const box = el('div', {class: 'rubric'});
  D.rubric.forEach(function(r){
    box.appendChild(el('div', {class: 'q'}, [el('p', {text: r[1]}),
      choice([1, 2, 3, 4, 5], ['1', '2', '3', '4', '5'], function(){ return sc[r[0]]; }, function(v){ sc[r[0]] = v; }, 'scale'),
      el('div', {class: 'ends'}, [el('span', {text: 'not at all'}), el('span', {text: 'completely'})])]));
  });
  if (KEY.mode === 'single'){
    box.appendChild(el('div', {class: 'q'}, [el('p', {text: 'Would you paint from this lesson?'}),
      choice(['yes', 'maybe', 'no'], ['Yes', 'Maybe', 'No'], function(){ return sc.would_paint; }, function(v){ sc.would_paint = v; }, 'three')]));
  }
  const note = el('textarea', {placeholder: 'Note (optional)', 'aria-label': 'Note on this lesson'});
  note.value = sc.note || '';
  note.addEventListener('input', function(){ sc.note = note.value; saveScores(scores); });
  box.appendChild(note);
  return box;
}

function build(){
  const main = document.getElementById('pics');
  D.pictures.forEach(function(P, p){
    const S = scores.pictures[p];
    const sec = el('section', {class: 'pic', id: 'pic-' + p});
    sec.appendChild(el('h2', {text: P.picture.replace(/-/g, ' ')}));
    if (P.photo){
      const ph = el('img', {alt: 'The photo'}); ph.src = P.photo;
      const fig = el('figure', {class: 'photo'}, [ph, el('figcaption', {text: 'The photo. Tap to enlarge.'})]);
      fig.addEventListener('click', function(){ fig.classList.toggle('big'); });
      sec.appendChild(fig);
    }
    Object.keys(P.sides).sort().forEach(function(side){
      const sc = S.scores[side];
      sec.appendChild(el('div', {class: 'lesson'}, [
        el('h3', {text: KEY.mode === 'pair' ? 'Lesson ' + side : 'The lesson'}),
        viewer(p, side, sc), el('h3', {text: KEY.mode === 'pair' ? 'Score lesson ' + side : 'Score it'}), rubric(sc)]));
    });
    if (KEY.mode === 'pair'){
      sec.appendChild(el('div', {class: 'q'}, [el('p', {text: 'Which would you paint from?'}),
        choice(['A', 'B', 'same'], ['A', 'B', 'No difference'], function(){ return S.prefer; }, function(v){ S.prefer = v; }, 'three')]));
    }
    const note = el('textarea', {placeholder: 'Note on this picture (optional)', 'aria-label': 'Note on this picture'});
    note.value = S.note || '';
    note.addEventListener('input', function(){ S.note = note.value; saveScores(scores); });
    sec.appendChild(note);
    main.appendChild(sec);
  });
  const done = el('section', {class: 'pic', id: 'pic-done'}, [el('div', {class: 'done'}, [
    el('h2', {text: 'All done'}), el('p', {id: 'summary'}),
    el('p', {text: 'Tap Copy scores and paste them back to Claude. They also stay saved on this phone.'})])]);
  main.appendChild(done);
}

function complete(p){
  const S = scores.pictures[p];
  const ok = Object.keys(S.scores).every(function(side){
    const sc = S.scores[side];
    return sc.real && sc.paintable && sc.agree && (KEY.mode !== 'single' || sc.would_paint);
  });
  return ok && (KEY.mode !== 'pair' || S.prefer);
}
function progress(){
  const n = scores.pictures.filter(function(_, p){ return complete(p); }).length;
  document.getElementById('summary').textContent = 'Scored ' + n + ' of ' + scores.pictures.length + ' pictures.';
}
function show(i){
  at = Math.max(0, Math.min(D.pictures.length, i));
  document.querySelectorAll('section.pic').forEach(function(s){ s.classList.remove('on'); });
  document.getElementById(at === D.pictures.length ? 'pic-done' : 'pic-' + at).classList.add('on');
  document.getElementById('count').textContent = at === D.pictures.length ? 'done' : (at + 1) + ' of ' + D.pictures.length;
  document.getElementById('back').disabled = at === 0;
  document.getElementById('next').textContent = at >= D.pictures.length - 1 ? 'Finish' : 'Next';
  document.getElementById('next').disabled = at === D.pictures.length;
  progress();
  window.scrollTo(0, 0);
}
function copy(){
  const text = JSON.stringify(scores, null, 2);
  const box = document.getElementById('copybox');
  function fallback(){
    box.style.display = 'block'; box.value = text; box.focus(); box.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
    status(ok ? 'Copied.' : 'Select all the text in the box and copy it.');
  }
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(function(){ status('Copied.'); }, fallback);
  } else fallback();
}

restore();
build();
document.getElementById('back').addEventListener('click', function(){ show(at - 1); });
document.getElementById('next').addEventListener('click', function(){ show(at + 1); });
document.getElementById('copy').addEventListener('click', copy);
show(0);
})();
"""


def page(data: dict, key: dict) -> str:
    title = "Blind A/B scores" if data["mode"] == "pair" else "Lesson scores"
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    key64 = base64.b64encode(json.dumps(key, sort_keys=True).encode("utf-8")).decode("ascii")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head><body>"
        f'<header><h1>{escape(title)}</h1><span class="count" id="count"></span></header>'
        '<main><p class="small">Score each lesson from its step pictures, paints and words. Swipe the picture or '
        'tap the arrows for the next step. Tap Worst step on any step that is the worst.</p>'
        '<div id="pics"></div><p id="status"></p><textarea id="copybox" readonly aria-label="Scores"></textarea></main>'
        '<footer><button type="button" id="back">Back</button><button type="button" id="copy">Copy scores</button>'
        '<button type="button" id="next">Next</button></footer>'
        f'<script type="application/json" id="data">{payload}</script>'
        f'<script type="text/plain" id="key">{key64}</script>'
        f"<script>{SCRIPT}</script></body></html>"
    )


class Invalid(ValueError):
    pass


def check_scores(s: dict) -> list[str]:
    """What's wrong with a scores JSON, or [] when it can be saved."""
    out = []
    if not isinstance(s, dict) or s.get("format") != FORMAT:
        return [f"not a {FORMAT} scores file"]
    if not s.get("round"):
        out.append("no round")
    if s.get("mode") not in ("single", "pair"):
        out.append("mode must be single or pair")
    for p in s.get("pictures") or []:
        name = p.get("picture", "?")
        sides = set((p.get("lessons") or {}).keys())
        if sides != ({"A"} if s.get("mode") == "single" else {"A", "B"}):
            out.append(f"{name}: lessons must be {{A}} in single mode, {{A, B}} in pair mode")
        for side, sc in (p.get("scores") or {}).items():
            for k, _ in RUBRIC:
                v = sc.get(k)
                if v is not None and v not in (1, 2, 3, 4, 5):
                    out.append(f"{name} {side}: {k} must be 1 to 5 or null, not {v!r}")
            if sc.get("would_paint") not in (None, "yes", "maybe", "no"):
                out.append(f"{name} {side}: would_paint must be yes, maybe or no")
            for w in sc.get("worst_steps") or []:
                if not isinstance(w, dict) or not isinstance(w.get("n"), int):
                    out.append(f"{name} {side}: a worst step needs its number n")
        if p.get("prefer") not in (None, "A", "B", "same"):
            out.append(f"{name}: prefer must be A, B or same")
    if not s.get("pictures"):
        out.append("no pictures")
    return out


def import_scores(path: Path, dest: Path = SCORES_DIR, force: bool = False) -> dict:
    """Save a scores JSON the page copied as scores/<round>.json on the bench."""
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = check_scores(s)
    if problems:
        raise Invalid("; ".join(problems))
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in s["round"])
    out = Path(dest) / f"{safe}.json"
    if out.exists() and not force:
        old = read_json(out)
        if old != s:
            raise Invalid(f"{out} already holds scores for this round (saved {old.get('saved_at')}); pass --force")
    write_json(out, s)
    unscored = [p["picture"] for p in s["pictures"]
                if any(sc.get(k) is None for sc in p["scores"].values() for k, _ in RUBRIC)]
    return {"saved": str(out), "pictures": len(s["pictures"]), "not_fully_scored": unscored}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make", help="write the page")
    p.add_argument("--round", required=True, help="the round's name, e.g. baseline-1.12.1 or s1-peel")
    p.add_argument("--out", required=True)
    p.add_argument("--lesson", action="append", default=[], help="single mode: a lesson folder (repeat per picture)")
    p.add_argument("--pair", nargs=2, action="append", default=[], metavar=("DIR_1", "DIR_2"),
                   help="pair mode: two lesson folders of one picture (repeat per picture)")
    p.add_argument("--seed", type=int, help="pair mode: the seed for the sides (default: from the round's name)")
    p = sub.add_parser("import", help="save a copied scores JSON on the bench (spike/experiments/bench/scores/)")
    p.add_argument("scores")
    p.add_argument("--force", action="store_true")
    sub.add_parser("format", help="print the scores JSON format")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "make":
            plan = plan_round(a.round, [Path(x) for x in a.lesson] or None,
                              [(Path(x), Path(y)) for x, y in a.pair] or None, a.seed)
            out = make(plan, Path(a.out))
        elif a.cmd == "import":
            out = import_scores(Path(a.scores), force=a.force)
        else:
            print(dumps(SCORES_FORMAT), end="")
            return 0
    except (ValueError, FileNotFoundError) as err:
        print(json.dumps({"problems": [str(err)]}))
        return 1
    print(json.dumps({**out, "problems": []}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
