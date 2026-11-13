# Step 6: text

## 6a. Draft
`draft-text --lesson <lesson>`. It writes `text.json`: for every step, numbered lines built from the plan, the
outlines, the paints, the technique, and the stroke cards (let it dry, rinse, where, the paints in order, mix
once, the brush and how to load it, the motion, what it should leave, two or three coats, watch out, step back).

You don't rewrite those. You add what only this photo needs, and you fix a line that reads wrong for this subject.

## 6b. For every step, write
Read the step's picture (`NN_<id>.png`) and its lines, then in that step's entry in `text.json`:
- **`summary`**: one sentence under 90 characters saying what the step paints.
- **`tip`**: one to three sentences only this photo needs. In order of importance:
  - **the light**: the first step's tip says where the light comes from; every later tip about a highlight keeps
    to that side;
  - **shape and placement** for a step that blocks in a shape: its proportions and where its parts sit ("the head
    is almost as wide as the body, and sits on its upper right");
  - **order inside the step** when there is one ("the cap first, then the bib joined to it on the right");
  - **direction**: which way the strokes run on this thing ("pull each stroke along the branch, thick at the trunk
    end");
  - **what to leave showing**, when the picture depends on it.
  No percentages. Inches or "as the Where picture shows".
- **`paint_notes`** (a list, when needed): a paint `mix` called unreachable ("as close as these tubes get"); a
  see-through tube color over something darker (the research's opacity table, section 3: yellows and student reds
  are see-through, so "paint it twice, letting the first coat dry").

## 6c. Fix the drafted lines that don't fit
A card is written for the stroke in general, so a line can read oddly here: the curved-strokes card says "down
each rib of a pumpkin" on a bird's chest; the small-circles card mentions clouds on a sun; the liner card says
"for branches" on an eye. For each such line, rewrite its `text` for this subject, **keeping what the card
teaches** (the motion, the load), and add `"edited": true` to the line so `draft-text` leaves it alone. To drop a
line that doesn't apply, set its `text` to `""` and `"edited": true`.

Don't add technique the cards and research don't have. Don't shorten a line to save space: there's no word limit
on a step, only on a line (40 words; a longer line is two moves, so split it).

Run `draft-text` again after any change to the plan or the pictures: it redrafts the data lines and keeps yours.
