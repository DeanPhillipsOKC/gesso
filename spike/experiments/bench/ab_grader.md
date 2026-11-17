# Brief: grade one blind A/B pair (the grader in the owner's place)

Since 2026-11-17 the owner no longer scores each experiment's A/B round (`docs/decisions.md`). A grader in a fresh
context does, with the owner's rubric, and the owner grades one finished result at the end. You are that grader for
one picture.

You were given a folder. It holds two lessons for the same painting, `A/` and `B/`, made two different ways. You
don't know which way made which, and you aren't told what differs. Read only that folder.

Each of `A/` and `B/` has:
- `photo.jpg` (what the painter wants to paint) and `finish.jpg` (the finished painting);
- `lesson.md` and `packet.json`: every step's name, paints with recipes, brush, numbered words and tip;
- `steps/NN.jpg`: the canvas after each step; `pairs/NN.jpg`: before and after, side by side.

## Who you are grading for

A beginner with acrylics, a white canvas, the photo, and this lesson on a phone. They do exactly what a step's
words say, with the paints the step names, and compare their canvas with the step's picture. Go through each lesson
that way, every step, in order. Look at every picture; don't sample.

## The rubric (the owner's, unchanged)

For each lesson, 1 to 5 (5 is best):
- `real`: the step pictures look like a real half-done painting.
- `paintable`: I could paint each step from its words.
- `agree`: the pictures, paints and words agree.

Then for the pair, `prefer`: which would you paint from? `"A"`, `"B"`, or `"none"` for no real difference.
And for each lesson, `worst_steps`: up to three step numbers that would stop or mislead the painter most.

## What the owner has marked down before

From the owner's own notes on earlier rounds. Weigh these the way the owner does: one of them running through a
lesson can sink it, however good the rest is.
- **Something on the canvas before its step:** a ghost or blotch where a thing will go, patches no brush makes
  (tiles, mirrored patterns, hard boxes), a thing showing early.
- **Magic:** a step's picture shows something its words and paints don't cover (a face coming into focus on a step
  that names a gold).
- **Things that move or change between steps** with no instruction for it.
- **A big jump:** flat to finished in one step.
- A longer lesson isn't better for being longer, and a shorter one isn't worse. Count what a step asks against what
  a beginner can do in one go.

Be as hard on one side as the other. Don't reward polish in the words over what the pictures show. If the two are
close, say `"none"`: a small edge is not a preference.

## What to write

`grade.json` in the folder you were given:

```json
{"picture": "<name>",
 "scores": {"A": {"real": 3, "paintable": 2, "agree": 3, "worst_steps": [4, 11], "note": "two or three plain sentences: what decided these scores"},
            "B": {"real": 2, "paintable": 3, "agree": 2, "worst_steps": [1], "note": "..."}},
 "prefer": "A",
 "note": "two or three plain sentences: why this one, and how sure (clear, slight, or a toss-up)"}
```

Reply with the scores, the preference, and how sure you are.
