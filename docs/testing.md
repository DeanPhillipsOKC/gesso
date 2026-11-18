# Tests

The tests are in `spike/tests/` (`unittest`, no network, no API key, no model files). There are two sets:

| Set | Command | When | Time on 4 cores |
|---|---|---|---|
| Quick | `python spike/tests/suite.py --quick` | after every code change, while working | about 13 seconds |
| Full | `python spike/tests/suite.py` | before merging a pull request that changes code | about 2 minutes |

Run tests only when a change could cause a regression (owner's call, 2026-11-17). Code means program files: the
Python and JavaScript under `spike/`. A pull request that changes no code (docs, skills' instructions, techniques,
elements, cards, palettes, bench results, lesson runs, `site/`) runs no suite. If it changes a file the tools load
(techniques, elements, cards, palettes), run only that loader's test: `python spike/tests/suite.py test_elements
test_yaml_files`.

Both run from the repo root with the venv's Python. Pass files, classes, or single tests to run only those
(`python spike/tests/suite.py test_aids test_publish_v2.PublishV2Tests`). `--jobs N` sets the number of worker
processes (one per core by default).

`python -m unittest discover -s spike/tests` still runs everything in one process, as before. It gives the same
results in about 5 minutes; use it when a test misbehaves only under the runner.

## How the suite is kept fast (#87)

- **The fixture lessons are built once per run.** The three fixtures (chickadee, lavender balloon, red sailboat) are
  sealed version 3 runs made small: each one's plan, canvas, chain, chain checker's answers and stage writers'
  words, at 0.4 of the size (`spike/tests/fixtures/lessons/`, made by `spike/tests/make_fixtures.py`).
  `spike/tests/lessons.py` builds each through the tools once, in stages (`chained`, `built`, `published`,
  `checked`, `worded`), into a folder all the workers share, and hands each test a copy. A test that needs a
  fixture lesson asks for one with `lessons.lesson(name, stage)`, and for what build-steps kept with
  `lessons.built(name)`; it doesn't run `build-steps`, `step-aids`, `mix`, or `publish` on a fresh folder unless
  that tool is what it tests.
- **Stroke cards and element files are parsed once per process** (`spike/yaml_files.py`), and again only when a file
  changes. publish used to parse all 28 stroke cards about 60 times.
- **Classes run in parallel**, one worker per core, the slow ones first.
- **The quick set leaves out the classes marked `@lessons.slow`**: the ones that build or publish a fixture lesson.
  Mark a new class slow when it takes more than a second or two.

When adding a test, prefer a small made-up scene (like test_erase3's scene and stand-in model, which
`test_steps3.py` runs the tools on) where the real picture isn't the point, and a shared fixture lesson where it is.
