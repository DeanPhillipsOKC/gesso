"""Make the test fixtures (fixtures/lessons/<name>/) from three sealed version 3 runs (#238).

    python spike/tests/make_fixtures.py output/chickadee_skill_20261118-091227 \
        output/balloon-lavender_skill_20261118-094526 output/red-sailboat_skill_20261118-161541

Each fixture is what `erase` and the run's helpers left, made small enough to keep in git: plan.json, canvas.json,
the chain (P<nn> as JPEG, D<nn> and C<nn> as 1-bit PNG) at 0.4 of the size, chain.json without the render numbers,
the chain checker's answers, and the stage writers' out.json. tests/lessons.py turns one back into a lesson folder:
the finish is the last P, and chain.json's `made_for` is worked out again for the small finish. Run this only to
replace a fixture: the tests' numbers are measured on these files.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures" / "lessons"
SCALE = 0.4
QUALITY = 80
NAMES = {"chickadee": "chickadee", "balloon-lavender": "lavender-balloon", "red-sailboat": "red-sailboat"}


def make(run: Path) -> Path:
    name = NAMES[run.name.split("_skill_")[0]]
    dst = OUT / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "chain").mkdir(parents=True)
    shutil.copyfile(run / "canvas.json", dst / "canvas.json")
    plan = json.loads((run / "plan.json").read_text(encoding="utf-8"))
    stem = run.name.split("_skill_")[0]
    plan["photo"] = next(f"photos/{p.name}" for p in (HERE.parent.parent / "photos").glob(f"{stem}.*"))  # in git
    (dst / "plan.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    kept = json.loads((run / "chain" / "chain.json").read_text(encoding="utf-8"))
    chain = {"units": kept["units"], "again": kept.get("again") or {}}
    (dst / "chain" / "chain.json").write_text(json.dumps(chain, indent=1) + "\n", encoding="utf-8")
    for p in sorted((run / "chain").glob("P[0-9][0-9].png")):
        img = Image.open(p).convert("RGB")
        size = (round(img.width * SCALE), round(img.height * SCALE))
        img.resize(size, Image.LANCZOS).save(dst / "chain" / f"{p.stem}.jpg", quality=QUALITY)
        for kind in "DC":
            m = Image.open(run / "chain" / f"{kind}{p.stem[1:]}.png")
            small = np.array(m.resize(size, Image.NEAREST)) > 0
            Image.fromarray(small).save(dst / "chain" / f"{kind}{p.stem[1:]}.png", optimize=True)
    answers = run / "chain" / "looks" / "answers.json"
    if answers.exists():
        shutil.copyfile(answers, dst / "answers.json")
    words = {s.name: json.loads((s / "out.json").read_text(encoding="utf-8"))
             for s in sorted((run / "words").glob("stage-*")) if (s / "out.json").exists()}
    (dst / "words.json").write_text(json.dumps(words, indent=1) + "\n", encoding="utf-8")
    return dst


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(make(Path(arg)))
