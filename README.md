# Gesso

Turn a photo into a step-by-step painting lesson at your skill level, in acrylic or oil. Each step
shows what the canvas should look like when you finish it and how to get there.

Unlike asking an image model to "show the steps," Gesso plans the painting the way a teacher
would, using real techniques for the medium and the painter's level, and generates each stage from
that plan.

Early days: see [the vision](docs/vision.md) for where it's headed.

## Running the pipeline spike

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r spike/requirements.txt
# put OPENAI_API_KEY and ANTHROPIC_API_KEY in .env (see .env.example)
python spike/run.py photos/your-photo.jpg                 # full quality, Claude variant
python spike/run.py photos/your-photo.jpg --quality low   # cheap test run
```

Each run writes a folder under `output/` with every image, `lesson.json`, and `lesson.html`.
`python spike/contact_sheet.py output/<folder>` tiles the images into one picture.
