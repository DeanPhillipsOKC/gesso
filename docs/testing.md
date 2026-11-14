# Tests

The tests are in `spike/tests/` (`unittest`, no network, no API key, no model files). There are two sets:

| Set | Command | When | Time on 4 cores |
|---|---|---|---|
| Quick | `python spike/tests/suite.py --quick` | after every change, while working | about 11 seconds |
| Full | `python spike/tests/suite.py` | before opening or merging a pull request | about 1 1/2 minutes |

Both run from the repo root with the venv's Python. Pass files, classes, or single tests to run only those
(`python spike/tests/suite.py test_aids test_publish_v2.PublishV2Tests`). `--jobs N` sets the number of worker
processes (one per core by default).

`python -m unittest discover -s spike/tests` still runs everything in one process, as before. It gives the same
results in about 5 minutes; use it when a test misbehaves only under the runner.

## How the suite is kept fast (#87)

- **The fixture lessons are built once per run.** `spike/tests/lessons.py` builds each of the three fixtures
  (chickadee, lavender balloon, red sailboat) through the tools once, in stages (`outlined`, `aided`, `published`,
  `checked`), into a folder all the workers share, and hands each test a copy. A test that needs a fixture lesson
  asks for one with `lessons.lesson(name, stage)`; it doesn't run `build-steps`, `step-aids`, `mix`, or `publish`
  on a fresh folder unless that tool is what it tests.
- **`build_steps.build` remembers its last few answers in a process.** Every tool on a version 2 lesson builds the
  steps (build-steps, step-aids, draft-text, check, and publish through check); with the same inputs in one
  process, the second and later builds are a copy of the first. From the command line each tool is its own
  process, so nothing changes there. Its key covers the inputs and the tuned numbers in `build_steps`, `from_finish`,
  and `outline`; a test that patches one of their functions should clear `build_steps._built` first.
- **Stroke cards and element files are parsed once per process** (`spike/yaml_files.py`), and again only when a file
  changes. publish used to parse all 28 stroke cards about 60 times.
- **Classes run in parallel**, one worker per core, the slow ones first.
- **The quick set leaves out the classes marked `@lessons.slow`**: the ones that build or publish a fixture lesson,
  or run the outline model. Mark a new class slow when it takes more than a second or two.

When adding a test, prefer a small made-up scene (like `scene()` in `test_pipeline_v2.py`) where the real picture
isn't the point, and a shared fixture lesson where it is.
