# v3's words, frozen (the baseline for pipeline v4's words spikes)

The three v3 lessons the v3 gate used, as made hands-off on 2026-11-18 (POC 2.0.0) and as they are on the lessons
site. Lesson runs live in `output/`, which isn't in the repository, so what v4's yardstick and words spikes need
of them is kept here (`docs/design/pipeline-v4-plan.md`; #174, #254 to #256). Nothing here is rebuilt: a spike
compares new words with these, on these pictures.

Each of `highland-cow/`, `sleeping-cat/` and `birch-grove/` holds:

- `RUN`: the lesson folder's name.
- `photo.jpg`, `finish.jpg`, `steps/NN.jpg`, `lesson.md`, `packet.json`: the painter's packet, as
  `spike/experiments/bench/packet.py` writes it (canvas crops, 1200 px on the long side). The before picture of
  step N is `steps/N-1.jpg`, and a blank canvas for step 1. `packet.py`'s `pairs/` are left out; they are these
  pictures side by side.
- `data/`: the run's `plan.json`, `text.json`, `lesson.json`, `mixes.json`, `canvas.json`, and `words/` (the fact
  sheet `sheet.json`, `dropped.json`, and each stage writer's folder less its pictures).

A grader or a student reader gets a copy of the packet files only, in a folder outside the repository. `data/`
holds the plan, and next to it in `bench/` are saved scores.

Not kept: the chain's renders and the step pictures at full size (about 250 MB a lesson). A spike that needs them
makes the lesson again, and says so.
