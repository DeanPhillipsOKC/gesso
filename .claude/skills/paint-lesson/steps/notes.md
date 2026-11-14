# Step 8b: notes (`notes.json`)

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
 "photo_prep": {"subject": "...", "found": "what else was in the image, or 'just the picture'",
                "action": "cropped with crop (box [x0, y0, x1, y1]) | none", "why": "..."},
 "canvas_fit": {"canvas": "11 x 14 in, portrait", "mode": "crop", "why": "...", "lost": "..."},
 "beginner_version": {"made": true, "found": "the answers to the four questions",
                      "list": "what you dropped, merged, and turned into marks", "why": "...",
                      "busy": {"photo": {"fine_texture": 0.103, "...": "as the busy tool recorded it, untouched"},
                               "beginner": {}, "finish": {}}},
 "beginner_check": {"summary": "what the check found overall",
                    "diagrams": {"<step id>": {"noticed": "what made this step need a diagram",
                                               "pieces": "how you broke the shape down, and why",
                                               "checked": "how the pieces compare with the step image",
                                               "source": "beginner check | owner feedback, <date>"}},
                    "no_diagram": {"<step id>": "why the picture and words are enough"}},
 "merged_parts": {"<part id>": "why it was dropped and which part carries its paint"},
 "learned": ["what you'd do differently next time, anything the cards, the research, or this skill didn't
             cover, and any drafted line you had to rewrite (which card, which subject)"]}
```

- `read`, `technique`, `order`, `steps`, and `beginner_check` are required; every step id appears in `steps` (why this step, and why now) and in
  either `beginner_check.diagrams` or `beginner_check.no_diagram`. The seal checks this.
- `canvas_fit` always (every lesson is fitted to a canvas, `--canvas` or not); `beginner_version` whether you made one or not.
- `beginner_version.busy` is written by the `busy` tool (step 0c), never by hand. The seal wants its `photo` number,
  and with a beginner version its `beginner` and `finish` numbers too; if you lost them rewriting the notes, run
  `busy` again.
- List every filter you looked at, kept or not, with its image path relative to the lesson. Step pictures aren't
  filters: they're cut from the finish, so they get no `filters` entry.
- `merged_parts` is an empty object when no part was dropped in step 2c.
- Every technique in `techniques/` you didn't pick goes in `considered`.
