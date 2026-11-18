# Checker's brief: did each render change only what it was asked to? (pipeline v3)

You are checking edits made to an unfinished acrylic painting. Each edit was asked to take one thing out of the
painting, or to take one layer of paint off a thing. Some edits did only that. Some also changed another thing, and
some left part of the thing standing. You don't know how many of either there are; there may be none.

You were given one folder: a lesson's `chain/looks/`. Read nothing outside it.

## What you have

- `U01.jpg`, `U02.jpg`, ...: one picture an edit. It holds three pictures of the painting, stacked top to bottom
  (or side by side, left to right, when the painting is tall):
  1. before the edit;
  2. after the edit;
  3. the before picture again, with every place the edit changed tinted magenta.
- `asked.json`: for each picture (`look`), `goes` (what the edit was asked to take out or take off) and `stays`
  (the other things in the painting, which were to stay exactly as they are).

## What to do

For each picture, in order:

1. Read its `goes` and `stays`.
2. Look at picture 3 first. The magenta shows where to look. Is any magenta on a thing in `stays`, away from the
   thing that was to go?
3. For each thing in `stays`, find it in picture 1 and look at the same place in picture 2.
4. Then look at picture 2 where the thing in `goes` was.

Answer two questions.

**stray:** did the edit change a thing it wasn't asked to change? Say yes only when a painter who laid the two
pictures side by side would say a different thing is there now:

- a thing in `stays` that could be seen in picture 1 is gone in picture 2 (a rock, a tree, a row of bushes);
- a thing in `stays` is there but drawn as different shapes (other trees, rows in other places);
- picture 2 shows a new thing that picture 1 did not, and that isn't in `stays` (a new tree trunk, a new plant).

These are not stray changes: the ground, sky or background that now shows where the removed thing was; a thing in
`stays` painted in where it was hidden behind the removed thing; softer edges; a small shift of color; magenta on
the shadow or the rim of the thing that went. When `goes` starts with "only the last layer", the whole thing that
layer was on may be tinted: that is the thing drawn again without the layer, not a stray change.

**left:** when `goes` starts with "all of", is a clear, whole part of that thing still standing in picture 2 (some
of the trees, half of the bushes)? A faint smudge is not. When `goes` starts with "only the last layer", is that
layer still plainly there in picture 2 (the stripes it names, the knit it names)?

## What to write

Write `answers.json` in the folder: a list with one entry a picture, in order.

    [{"look": "U01", "stray": false, "left": false, "why": ""},
     {"look": "U02", "stray": true, "left": false, "why": "the gray rock right of the path is gone"}]

`why` is one short sentence when either answer is true, naming the thing and where it is. Then reply with one
line: how many pictures you read, which you marked, and for each of those `stray` or `left`.
