# Fault counter: count what's wrong in one painting lesson

You are checking one beginner acrylic painting lesson the way a careful painter would, step by step, and
counting its faults. You have only what a painter gets: the photo, the finished painting, each step's picture,
paints and words. You know nothing about how the lesson was made, and you don't need to.

Count, don't fix. Don't praise. Every fault you write down must point at something you can see in the packet:
a step, a place in a picture, a line of words. Two careful reviewers reading this brief should count the same
faults, so follow the definitions below exactly, and when in doubt use the tie-breaks.

## What you get

One packet folder. Read only inside it. Don't open other folders, the repository, git, or the web.

- `photo.jpg`: the picture the lesson paints from, cropped to the canvas.
- `finish.jpg`: the finished painting. The last step should look like it.
- `steps/NN.jpg`: step NN's picture, what the canvas should look like after it.
- `pairs/NN.jpg`: step NN-1 (left, BEFORE) beside step NN (right, AFTER). Step 1's BEFORE is a blank canvas.
- `lesson.md` and `packet.json`: each step's name, its paints (name, color as hex, recipe), brush, numbered
  words and tip, as the lesson page shows them. `packet.json` also gives the canvas size in inches
  (`canvas_in`, width then height).

You may use Python to crop, zoom, or measure a picture (pixels to inches: the picture's width is the canvas
width). Measure before you report a placement fault.

## How to work

1. Look at `photo.jpg` and `finish.jpg`. Say in one line what the painting is.
2. For every step, in order: look at `pairs/NN.jpg` (and `steps/NN.jpg` to zoom), then read its words and paints.
   Ask: what changed between BEFORE and AFTER? Do the words tell a beginner to make exactly that change, with
   those paints, in that place? Is the AFTER picture something a beginner's canvas could really look like at this
   point?
3. Write each fault down as you find it, with its class, severity, what you see, and where.
4. Then look across the lesson for faults no single step shows (a paint that no step's picture uses, a step that
   should have come earlier).
5. Write `faults.json` in the packet folder (format below).

## The eight classes

Each fault gets exactly one class. The examples are illustrations of the size and kind of thing that counts. They
are made up for pictures that aren't in this lesson (pumpkins, a barn, a fox, a lighthouse, pears on a table), so
they don't tell you where to look: look at every step for every class.

### A. Step pictures
The step picture shows something that isn't what a painter would have on the canvas after this step.
- **Ghosts:** something not painted yet already shows. The fox's dark legs show as faint shapes on the snow from the
  snow steps on, long before the fox step. The lighthouse's red bands show in the sky step.
- **Patches behind an object:** where a later object goes, the picture shows a color or texture that belongs
  somewhere else. Barn-red streaks in the field where the barn will stand, until the barn step.
- **Things change with no instruction:** something painted earlier changes shape or color in a step whose words
  don't mention it. The hills behind the barn change outline on the fence step. The pears' table turns darker on a
  step that only paints a pear's stem.
- **Not paint:** a pattern no brush makes. A mirrored, tiled, kaleidoscope-like pattern; a regular grid of dots;
  straight vertical seams; a hard rectangular edge; a smeared copy of a neighboring area; a smooth blur with no brush
  marks that looks like a photo filter.
- **Jumps:** one step goes from a flat coat to finished, dense detail (every leaf, all the fur, every blade of
  grass) that no beginner paints in one move. A pumpkin goes from one flat orange shape to fully modeled ribs,
  highlights and stem on a step whose tip says "just a few strokes".

### B. Outlines
One part's painted area has the wrong shape: it takes in a piece of what's around it, misses a piece of itself,
or has ragged, blobby edges or stray specks.
- The lighthouse's dark block-in has lumps of sky stuck to its side and loose specks floating off it.
- A thin railing is lumpy and twice as thick in places; a fox's tail takes a slab of the snow it lies on.
- The hills' painted area has a piece up in the sky that reaches the top edge.

A or B? B is about the edge of the area one step paints. A is about what the picture shows that the step didn't
paint (or shouldn't have). A blob of sky stuck to the lighthouse is B; lighthouse-colored ghosts in the sky three
steps before the lighthouse is A.

### C. Placement
The words put something in the wrong place or at the wrong size, compared with the step's own picture.
Measure in inches from the canvas edges.
- A tip puts the biggest pumpkin "just left of the center"; in the picture it's just right of it.
- "Its right side is at the right edge" for a barn roof that stops nearly an inch short.
- "The field's top is about 4 in from the bottom edge" where the visible field line is about 5 in.
- Two lines of one step giving two different sizes for the same thing ("3 in wide" and "2 1/2 in wide").
- A position given as a percentage or a tape mark instead of inches.

Count it only when the error is about 1/2 in or more on a canvas up to 12 in, or 3/4 in or more on a bigger one,
or the side is wrong.

### D. Paints
The paints a step names don't match the color its picture adds, or the paint list is wrong.
- "Paint the green pear" names Olive yellow; the picture adds a cool blue-green.
- A part's last step adds a lot of color it doesn't name: only about a quarter of what it adds is near its one
  paint, the rest is shadow violet and teal it never mentions.
- A paint listed for the lesson that no step uses, or two paints with different names and the same recipe.
- A swatch whose color is clearly not what its recipe makes (a warm brown from red and blue with no brown or
  yellow in it, which mixes a purple).

Count a color mismatch when a beginner holding the named paint would see it's a different color from what the
picture adds (another hue, or much lighter or darker), not a small shade difference.

### E. Text
A line of words is wrong or can't be acted on, apart from placement (C) and paint names (D).
- **Missing:** a visible change no line asks for (grass blades appear in a step about pumpkins).
- **Wrong result:** the stroke a line asks for wouldn't make what the picture shows (cross-hatched strokes for a
  smooth gradient; "tapped dabs" for what the picture shows as one flat, hard-edged shape).
- **Vague:** a beginner couldn't act on it ("add some highlights" with no where, which paint or which brush; a
  sky whose colors aren't named in order).
- **Wrong subject:** words written for another thing. A teapot's handle step says the strokes "make a cloud's bumpy
  top edge".
- **Contradiction:** the tip says to leave a gap for the barn door, and the picture fills it. A line that refers to
  a step that doesn't use what it says ("mix enough for step 8", and step 8 doesn't use it).

### F. Teaching
The words match the picture, but the way the lesson teaches would lead a beginner wrong.
- Waiting for each layer to dry where the effect needs wet paint, so a soft blend comes out streaky and separate.
- A word a beginner doesn't know, used as if they did, with nothing on the step to explain it (a paint "load" such
  as "creamy" or "a light load", "scumble", "glaze").
- Painting over a layer without saying to let it dry first, where wet paint would mix into mud.
- **Too much:** several different kinds of moves in one step (not one big move like a whole-sky blend).
- **Flat:** one color or one mark for an area the picture shows with several values or a texture (a pumpkin with a
  lit side and a shadow side), with no word on how to build it up.
- **Order:** a step that only makes sense earlier or later (details before the base they sit on).

E or F? E is a sentence that's wrong or unclear. F is a sound sentence that teaches the wrong move or leaves out
how to do it.

### G. Site
How the lesson is presented, not what it says: steps out of order or numbered with a gap, a missing or broken
step picture, the photo or finish missing, a step picture identical to the one before when the words say to paint
something. Most site faults (a lesson missing from its page, an old version shown in place of the new one, wrong
numbers in the lesson history) can't be seen in this packet.

### H. Tooling
A symptom of a tool going wrong that shows in what the painter gets and isn't a painting fault: a tool's own note
leaking into the words ("card small-circles has no load, so no load line"), a placeholder such as `None`, `NaN`,
`TODO` or an internal id (`sky-1`) where a name should be, a line repeated word for word in one step. Most tool
faults (a diagram drawn all gray, a render refusing to start, a check missing a problem) can't be seen in this
packet.

### G and H: count only what you can see
The packet can't show the lesson page's layout, its links, the close-ups and diagrams, the site, or how the run
went. Count a G or H fault only when its symptom is in the packet. Write down in `not_visible` what the packet
can't show you for G and H, so a zero there isn't read as "no faults".

## One fault, one class, one count
- **Cause first.** When pictures and words disagree, ask which is wrong compared with the finish. The picture
  wrong: A or B. The words wrong: C, D, E or F.
- **Tie-break order** when a fault fits two classes: A, B, C, D, E, F, G, H (take the first that fits).
- **Per step.** A fault visible in several steps is counted once in each step a painter meets it in (a tiled patch
  that shows from step 7 to step 13 is 7 faults). Give the later ones `same_as` with the first one's `id`, so a
  count of distinct faults is possible too.
- **Two things wrong in one step are two faults**, even of one class.
- Don't count taste (you'd have chosen a different color). Don't count render noise smaller than a brush mark.

## Severity
- `blocker`: a beginner couldn't do the step, or following it gives something clearly wrong (a pattern no brush
  makes, the wrong color family, the wrong side).
- `major`: a beginner would notice, be confused, or end up visibly different from the picture, but could recover.
- `minor`: a careful reader notices; it barely changes the result.

## Output: `faults.json` in the packet folder

```json
{"packet": "p03",
 "painting": "one line: what the painting is",
 "steps": [
   {"n": 1, "id": "sky-blend", "faults": []},
   {"n": 12, "id": "barn-roof", "faults": [
     {"id": "f7", "class": "A", "severity": "blocker",
      "sees": "a mirrored, tiled pattern in a strip under the roof's edge, nothing a brush makes",
      "where": "AFTER picture, x 30-62%, y 58-63% (about 4 1/2 to 9 in from the left, 6 in down)",
      "same_as": null}]}],
 "lesson_faults": [
   {"id": "f20", "class": "D", "severity": "minor", "steps": [],
    "sees": "Pale rose is in the paints list but no step's picture adds it", "where": "paints"}],
 "counts": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "G": 0, "H": 0},
 "distinct": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0, "G": 0, "H": 0},
 "worst_steps": [12, 9],
 "not_visible": {"G": "what the packet can't show for the site", "H": "what it can't show for the tools"},
 "summary": "two or three sentences: the patterns across the lesson"}
```

- Every step appears in `steps`, with an empty `faults` list when it has none.
- `id`s are unique in the file (`f1`, `f2`, ...). `same_as` is the `id` of the first time this fault showed, or
  null.
- `where` gives the picture (AFTER, BEFORE, or the words' line number) and a place: percent across and down, or
  inches from the canvas edges.
- `counts` is the number of faults per class, steps and lesson faults together, repeats included. `distinct`
  leaves out the ones with `same_as`.
- `worst_steps` are the one to three step numbers you'd fix first, worst first.
