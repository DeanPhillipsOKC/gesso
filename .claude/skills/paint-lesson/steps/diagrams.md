# Step 8a: beginner check and construction diagrams

A step image shows the canvas after the step, not how to get there. Go through every step as someone who has
never painted, with only that step's picture and words, and ask: **could I start this?** Nobody else will notice
what's missing.

**A step needs a construction diagram when any of these hold:**
- a shaped object appears whole in one step (a pumpkin, an animal, a person, a building, a boat);
- the outline is lumpy, segmented, or repeated parts (lobes, petals, a row of fence posts);
- lines whose placement depends on the object's structure (ribs on seams, fur following the body, a face's
  features, windows in perspective, branches forking off a trunk);
- you'd need to sketch it on scrap paper first;
- where things start or join isn't clear from the picture;
- an instruction needs more than a sentence for a shape, a stroke path, or an order of moves.

**Usually no diagram:** flat fills, skies and gradients, textures made by repeating one mark, and anything the
words make obvious. Say why for each in `no_diagram`.

**Also check the words against the picture** while you look, and fix any instruction that says something the
picture doesn't show.

## Breaking a shape into pieces
1. Name its structure: a pumpkin is lobes around a core; a sleeping cat is a round head against an oval body; a
   tree is a trunk that splits into Y's.
2. The biggest mass first, as one simple shape, where it sits.
3. Attached parts in order of size, back pieces `behind`. Repeated parts get smaller toward the edges.
4. Let the pieces set up later steps (the seams between lobes are where the ribs go; a later diagram can start from
   them as `done`).
5. Check against the step image and the finish: proportions, number of parts, where they attach. 2 to 4 panels,
   captions of a few words, the shape filling most of the box.

## The spec
Put `construct` on the step in `text.json`. Coordinates are a 100 x 100 box, y down; draw a wide, short area at
its real proportions (a 100 x 40 band), not stretched.

```json
"construct": {"title": "Build the big pumpkin from simple pieces", "paint": "Pumpkin orange",
  "stages": [
    {"caption": "A center oval", "add": [{"ellipse": [50, 58, 12, 21]}], "arrows": ["M 50 40 Q 40 58 50 76"]},
    {"caption": "A ( ) on each side, tucked behind",
     "add": [{"ellipse": [38, 60, 12, 19], "behind": true}, {"ellipse": [62, 60, 12, 19], "behind": true}]}]}
```

Shapes: `ellipse [cx, cy, rx, ry]` (optional `rotate`), `circle [cx, cy, r]`, `rect [x, y, w, h]` (optional
`round`), `path "<d>"` (filled, optional `opacity`), `line "<d>"` (stroked, `width`). Any shape can set `paint` (a
plan paint), `behind: true`, or `done: true`. `arrows` show only in their panel. A broken spec is left off the
page, so check `publish`'s `diagrams` count.

Look at your diagrams before moving on: **`publish` first** (the preview reads `lesson.json`, so a new or changed
diagram shows only after a publish), then `preview-diagrams --lesson <lesson>` draws each next to its step image
into `<lesson>/trials/diagrams.png` to Read.

Write what you noticed and decided into `notes.json` as `beginner_check` (step 8b). `publish` lists any diagram
without a note in `undocumented_diagrams`.
