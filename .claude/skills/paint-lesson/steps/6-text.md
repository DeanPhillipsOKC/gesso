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

## 6c. Adapt each stroke card for this painting
A stroke card is written for the stroke in general, with no subject, so it's never wrong but it can be vague: the
small-circles card says "a bumpy edge" on what is a plain round sun. The page shows a card open in the first step
that uses it; adapt that copy to what this step paints.

Run `card-adapt --lesson <lesson>`. For each card a step opens, it copies the card's `motion`, `result`, `then`,
`mistakes`, and `diagram` into `text.json` under `card_text.<step id>.<card id>`, with `"from": "<card id>"`. It
never overwrites a copy that's already there, so run it again after a plan change and take out what it lists as
`stale`. Then edit each copy. **Edit, don't rewrite**: never start a card from blank.
- **`motion`, `result`, `then`**: the same field saying the same thing about the brush, the motion, the load, and
  what it leaves, with the subject's words swapped in ("a bumpy edge" -> "the round edge of the sun"). No new
  technique, and no other brush.
- **`mistakes`**: the same ones, in the same order, each with its `mistake`, `why`, and `fix` reworded for this
  subject. Drop one that can't happen here; don't replace it or add one.
- **`diagram`**: the card's diagram, adapted. Keep its stages and their arrows. Swap each `paint` for the step's
  paints, by name. Where the example shape is wrong for this part (bumps for a sun), change it to the part's shape
  with construct's shapes (`steps/diagrams.md`). Reword the title and captions, saying the same thing.
- Leave `from` as it is. A copy you don't edit shows as the general card.

The page shows the adapted card with "Adapted for this painting from the ... card, not checked yet", the general card
folded under it, and the step's close-up beside the diagram as "Here". `check` fails a copy that drifted from its
card (a field missing or added, more mistakes, another brush, other diagram stages or arrows) and says what to put
back, and notes a card shown with no copy.

## 6d. Fix the drafted lines that don't fit
The drafted lines take the general card's words too. Where one reads oddly for this subject (the liner card's
"to taper a line" on an eye), rewrite its `text` for this subject, **keeping what the card teaches** (the motion,
the load), in the same words as your adapted card, and add `"edited": true` to the line so `draft-text` leaves it
alone. To drop a line that doesn't apply, set its `text` to `""` and `"edited": true`.

Keep the load words exactly as drafted ("Load: Creamy paint, a full load."): the page links them to the paint-load
card and shows their pictures only in that form (#99). In a tip, say how thick and how much only with the card's
words (thick, creamy, or thin paint; a full load, a light load, or wiped nearly dry).

Don't add technique the cards and research don't have. Don't shorten a line to save space: there's no word limit
on a step, only on a line (40 words; a longer line is two moves, so split it).

Run `draft-text` again after any change to the plan or the pictures: it redrafts the data lines and keeps yours.
