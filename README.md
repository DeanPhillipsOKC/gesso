# Gesso

Turn a photo into a step-by-step painting lesson at your skill level, in acrylic or oil. Each step
shows what the canvas should look like when you finish it and how to get there.

Unlike asking an image model to "show the steps," Gesso plans the painting the way a teacher
would, using real techniques for the medium and the painter's level. The finished painting is rendered
once, and every step is cut from it with free tools, so steps can't drift.

Early days: see [the vision](docs/vision.md) for where it's headed, and
[pipeline v2](docs/design/pipeline-v2.md) for how lessons are made now.

## Making a lesson

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r spike/requirements.txt
# put OPENAI_API_KEY in .env (see .env.example)
# (if HTTPS_PROXY is set and the proxy supplies the OpenAI key, as in a cloud session, OPENAI_API_KEY can stay unset;
#  a proxy that doesn't supply it gives a 401 "Incorrect API key" instead of "Missing credentials")
```

Then, in Claude Code: `/paint-lesson photos/your-photo.jpg` (optionally `--canvas 11x14`). The skill
(`.claude/skills/paint-lesson/`) writes a folder under `output/` with every picture, `lesson.json`, and a
self-contained `lesson-standalone.html`. The tools it runs are `python spike/tools.py <tool> --help`.

Tests: `python spike/tests/suite.py --quick` after a change, `python spike/tests/suite.py` before a merge (no network,
no API key; see `docs/testing.md`).
