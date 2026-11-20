# Brief: give the lesson its arc (pipeline v3.1)

Your step words are done and checked; they stay as they are. Now a second job, on the same lesson and in the same
folder.

The steps are not separate forms: the lesson has an arc, and you write it too. Nothing yet says what the painter
will learn, why the steps come in this order, or that a step repeats a stroke the painter already did. Everything
in the arc comes from the plan, the cards and the pictures: no new technique, and no stroke or paint the lesson
doesn't use.

## What you read

The files you read for the steps (`plan.json`, `steps.md`, `cards.md`, the pictures, `photo.jpg` and `finish.jpg`),
and two more:

- `words.md`: every step's words, as the painter reads them, after the checks.
- `stages.md`: the lesson's stages, each with its id, its steps and its end picture: the canvas at the end of a
  stage is the after half (right) of its last step's pair.

## What to write

- **The opening** (read once, before step 1):
  - `welcome`: two or three sentences on what the painter is about to make and what will make it sing (the
    subject, its focal point, the mood of the light), as a teacher would say it before the first brushstroke.
  - `light`: one or two sentences on where the light comes from in this painting and what it does to the things in
    it, since many steps put paint where the light falls or doesn't. Name the light by its source ("the window
    light", "the low sun"), not by a side.
  - `skills`: the two or three things this painting teaches a beginner. Each one is a stroke card the lesson uses
    (`card`, its id from the cards), with the steps that use it (`steps`, their numbers) and `how`: two or three
    sentences on what the stroke is, where in this painting it does its work, and what to watch for (from the
    card). Pick the cards that do the most work in this painting, not every card.
  - `road`: four to six sentences: every stage in order, what each one adds, and why the order (from the plan's
    `why`).
- **A stage's two lines**, for every stage in `stages.md`: `for`, one sentence of what the stage is for (shown at
  the top of the stage); and `end`, one sentence of what the canvas looks like at its end, from its end picture
  (shown after the stage's last step).
- **A step that points back** (`back`): give one to every step that repeats an earlier step's stroke card or one of
  its paints, where saying so helps a beginner: they've done this, and here is what's different this time (the
  paint, the brush, the size, where it goes). That is likely about half the steps. Skip a step only when the tie is
  empty ("the same paint" with nothing else to say), and point to the earlier step a painter would remember best,
  not always the one just before. `step` is the earlier step's number; it must share this step's stroke card or
  one of its paints. It adds to the step, and never replaces what the step says: the step must still say how. The
  page shows it as "As in step N: ...".

**No numbers and no side words in the opening or a stage's lines** (no inches, no left, right, top, bottom,
upper, lower, above, below, under, beside): the sheet measures a step, not a stage, so a tool can't check them
there, and a sentence with one is taken out. Name things by what they are. A back line is a step's line and follows
the step's rules (`brief.md`): its numbers and sides are checked against the sheet, and it names only its own
step's paints. Plain words, short sentences.

Write `arc.json` in your folder:

```json
{"opening": {"welcome": "...", "light": "...", "skills": [{"card": "<card id>", "steps": [3, 8], "how": "..."}], "road": "..."},
 "stages": {"<stage id>": {"for": "...", "end": "..."}},
 "steps": {"<step id>": {"back": {"step": 8, "text": "..."}}}}
```

`steps` holds only the steps that point back. Then reply with one line: anything you couldn't square.

If what you wrote fails a check, you are sent back once: read `arc-feedback.md` and write `arc-fix.json`, the whole
arc again in the same shape. What still fails after that is taken out.
