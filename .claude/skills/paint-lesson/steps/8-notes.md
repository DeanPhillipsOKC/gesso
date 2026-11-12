# Step 8: notes (`notes.json`)

The page's "How this lesson was made" folds show your reasoning. You've been keeping notes as you go; make them
complete now. Plain words, a sentence or two each:

```json
{"read": "a painter's read of the photo: what matters, what's hard, what the lesson should be about",
 "technique": {"why": "why this technique fits this photo and level",
               "considered": [{"name": "Block in, then build up", "why_not": "..."}],
               "how_chosen": "only if you didn't choose it (e.g. the owner named it)"},
 "order": "why the steps go in this order",
 "steps": {"<step id>": "why this step, and why now"},
 "filters": [{"label": "Reference", "tool": "simplify", "settings": "meanshift, strength 3",
              "image": "trials/simp3_ms.png", "why": "what you wanted to see", "result": "what you saw",
              "verdict": "kept | dropped"}],
 "throwaways": [{"script": "filters/sky_only.py", "for": "...", "steps": ["sky-glow"], "tries": 1,
                 "outcome": "what happened", "verdict": "kept | seeded a render | dropped",
                 "images": ["filters/01_sky-glow_filter.png"]}],
 "photo_prep": {"subject": "...", "found": "what else was in the image, or 'just the picture'",
                "action": "cropped with crop (box [x0, y0, x1, y1]) | none", "why": "..."},
 "canvas_fit": {"canvas": "11 x 14 in, portrait", "mode": "crop", "why": "...", "lost": "..."},
 "beginner_version": {"made": true, "found": "the answers to the four questions",
                      "list": "what you dropped, merged, and turned into marks", "why": "..."},
 "beginner_check": {"summary": "what the check found overall",
                    "diagrams": {"<step id>": {"noticed": "what made this step need a diagram",
                                               "pieces": "how you broke the shape down, and why",
                                               "checked": "how the pieces compare with the step image",
                                               "source": "beginner check | owner feedback, <date>"}},
                    "no_diagram": {"<step id>": "why the picture and words are enough"}},
 "long_steps_kept": {"<step id>": "why this step stays over the word budget"},
 "learned": ["what you'd do differently next time, and anything the research didn't cover"]}
```

- `read`, `technique`, `order`, `steps`, and `beginner_check` are required; every step appears in `steps` and in
  either `beginner_check.diagrams` or `beginner_check.no_diagram`. The seal checks this.
- `canvas_fit` only with `--canvas`; `beginner_version` whether you made one or not.
- List every filter you looked at, kept or not, with its image path relative to the lesson.
- Every technique in `techniques/` you didn't pick goes in `considered`.
