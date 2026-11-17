# Brief: write one stage's words from its fact sheet (the combined lesson, #210)

You write the words for one stage of a beginner acrylic painting lesson. Read only the folder you were given:

- `steps.json`: the stage's steps, each with its name, part, paints, brush, stroke, its before-and-after picture
  (`pair`), and its drafted lines (numbered). Also the light's direction and the whole lesson's step list, so you
  know what comes before and after this stage.
- Each step in `steps.json` also has `meant`: what the lesson's plan says the canvas shows when the step is done. It
  was written before the pictures were made. It tells you what the step is for. The after picture is still what the
  painter compares with: write to the picture, and where the picture and `meant` disagree (the picture already
  shows something `meant` says comes later, or lacks something it names), say what the picture shows.
- `pair-NN.jpg`: the canvas before the step (left) and after it (right). Look at every one.
- `facts.md`: what was measured on each step's picture: sizes and distances in inches, the edges it reaches,
  where its paint lands, its marks, what's under it and next to it.
- `photo.jpg` and `finish.jpg`: what the painter wants to paint, and the finished painting.

The painter is a beginner with acrylics, a white canvas, and this lesson on a phone. They do what a step's words
say with the paints it names, then compare their canvas with the step's after picture.

## What to write, for every step

- **`summary`**: one sentence under 90 characters saying what the step paints.
- **`tip`**: one to three sentences only this photo needs. In order of importance:
  - **the light**: the lesson's first step says where the light comes from; a later tip about a highlight keeps to
    that side;
  - **shape and placement**, for a step that blocks in a shape: its proportions and where it sits;
  - **order inside the step**, when there is one;
  - **direction**: which way the strokes run on this thing;
  - **what to leave showing**, when the picture depends on it.
- **`paint_notes`** (only when needed): a see-through paint over something darker ("paint it twice, letting the
  first coat dry"), or a paint the tubes can only come close to.
- **`lines`** (only when needed): a drafted line that reads wrong for this subject, rewritten, by its number. Keep
  what it teaches (the motion, the load) and keep load words exactly as drafted ("Load: Creamy paint, a full
  load."). `""` drops a line that doesn't apply. Never rewrite the Where line.

The words must match the after picture: what it adds, where, and what stays as it was. If the picture adds
something the step's paints and words don't cover, say what the picture shows rather than ignore it.

## The rules for numbers and sides

This is the point of the experiment. Every number, side and position you write is checked by a tool against
`facts.md`, and a claim that isn't there fails.

- **Use only numbers and sides that are on the sheet.** Say a length in the ruler value given first ("2 3/4 in"),
  never the decimal in brackets.
- **Say what each number measures**, in the sheet's words: "its top is about 1/2 in from the top edge", "about
  3 in wide", "its middle is about 8 in from the left edge". A bare "about 3 in" is a fault.
- **Say what a side is of.** "Right of the hull", "on the right side of the balloon", "at the right edge (of the
  canvas)". Not "on the right", "below it", "the shape above".
- **Name parts by the sheet's names** ("the balloon", "the rolling fields"), and an earlier step's marks by their
  paint ("the Deep balloon red stripe"), so the tool can find what you mean.
- **"Most of it on the left side"** means at least half of what the step adds is in that half (the sheet's halves).
- **When the picture shows something the sheet doesn't measure** (a piece of a part, a gap, a highlight's spot), say
  it without a number or a side ("as the Where picture shows", "where the after picture has it"), or leave it out.
- No percentages, ever. Inches or "as the Where picture shows".

## What to write to

`out.json` in your folder:

```json
{"steps": {"<step id>": {"summary": "...", "tip": "...", "paint_notes": [], "lines": {"6": "rewritten line 6"}}}}
```

Every step in `steps.json` gets an entry with a summary and a tip. Leave out `paint_notes` and `lines` when you
change nothing.

If you're sent the checker's failures afterwards (`feedback.md`), fix each one and write the whole `out.json`
again. A sentence that still fails after that is taken out.

Reply with one line: how many steps you wrote, and anything in the pictures that the words couldn't square.
