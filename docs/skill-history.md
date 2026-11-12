# Why the paint-lesson skill's rules are what they are

The skill (`.claude/skills/paint-lesson/`) keeps only the rules, so a run reads short, current instructions at
each step. This is where the runs that taught each rule are kept. Add to it when a run teaches something new.

## Photo and canvas
- **Crop screenshots first** (2026-11-11): the owner sent a shop page with the painting in the middle.
- **Fit the canvas** (2026-11-11): the owner paints mostly on 11x14, some 24x30 and 10x10, and the lesson should
  match the real canvas's shape so nobody has to imagine how a wide picture fits.
- **Beginner version** (2026-11-11): the balloon lesson kept a village of tiny houses, textured clouds, and every
  lavender stalk, and one step jumped from flat purple rows to thousands of stalks.

## Reference and finish
- **Mean shift for outlines and small dots**: Kuwahara broke the cat's face apart, and wiped out the stars on the
  tree-of-life picture (2026-11-11).
- **Pass the photo to the finish** (trees, 2026-11-10): a Kuwahara reference alone turned a cream-gold sky into
  blue and purple patches and needed a paid repaint. With a beginner version, pass it, not the original, or the
  original's detail flows back in.
- **Keep each area's share** (tree of life, 2026-11-11): the frame snaps to fixed shapes, and the lake got
  squeezed to a strip.

## Plan
- **Measure positions** (balloon, 2026-11-11): "right of center" was wrong and cost a paid redo.
- **Give edges as numbers** (balloon rerun, 2026-11-11): three redos were renders stopping the sky short.
- **Let the brush keep moving, and build shapes from pieces** (pumpkin, owner's notes, 2026-11-11).
- **Texture in passes** (balloon, 2026-11-11, twice): "they're straight lines, then they're textured."

## Images
- **Throwaway filters**: on the cat and pumpkin (2026-11-10) both tries failed where a later layer hid what the
  step had to show. On the trees, masking the trees and inpainting made the sky step, and a seeded render fixed its
  mark for $0.018.
- **Lock finished areas**: the step review found drift in a third of its problems; the backward pass cut the last
  pumpkin step from changing 27% of the canvas to 11%.
- **Lines keep their shape** (balloon run, 2026-11-11): straight paths turned curved two steps later.
- **The main subject keeps its shape** (chickadee, 2026-11-11): the finish drew the bird smaller and more upright,
  and the head step's cap differed from the feather step's.
- **No split edges** (balloon run, 2026-11-11): a texture cut by area, dabbed above a straight line and flat below.
- **Cut coats and passes from the finish** (spike #8, 2026-11-12): beat rendered passes on the lavender.
  `--in-place` (2026-11-12): the chickadee run found a copy can't be sealed hands-off.

## Text
- **Computed recipes** (five lessons, 2026-11-11): recipes written by eye missed by Delta E 11 on average, the
  mixer by 2.
- **Word budget** (balloon rerun, 2026-11-11): new rules doubled the text to about 160 words a step.
- **Never trim sizes, positions, or counts** (balloon trim, 2026-11-11): halving the text dropped the balloon's
  width, the number of rows, and the trunk's size, and the reviewer's vague findings went from 3 to 8.
- **Show, don't tell** (owner, 2026-11-11).
- **Values tables add, never replace; a color sequence isn't values** (balloon run, 2026-11-11): "blend down as in
  the values table" told the painter nothing about the sky's colors.

## Reviews
- **Text review** (#24 spike, 2026-11-11, balloon and pumpkin, against the owner's blind labels): it agreed on 8 of
  15 steps. It caught what the text leaves out; it missed how to get depth and texture and letting paint dry, so
  `flat`, `layering`, and the repeat-mark diagram rule were added. It rated steps `ok` while listing real problems,
  so the verdict now follows the problems.
- **Check `ok` steps against the finish** (chickadee, 2026-11-12): the reviewer rated the branches step ok, but its
  branch thickness and bend didn't match the finish.
- **Reviewers use the venv** (chickadee, 2026-11-12): a reviewer couldn't zoom without PIL.

## Diagrams
- **The beginner check** (2026-11-11): the owner had to point out that the pumpkins needed construction diagrams.
  The checks also found a trunk said to pass "left of the sun" that forks around it, and a cat head said to be a
  third of the body's width that is about half.
- **Publish before previewing diagrams** (sailboat, 2026-11-12): the preview reads `lesson.json`, so a new diagram
  didn't show.

## Seal
- **Hands-off** (owner, 2026-11-12): the app won't have anyone to tweak a lesson, so the tool has to stand on its
  own. The seal checks what the skill used to only ask for, because two hands-off runs each skipped a small rule
  late in a long run (the skill was 8,000 words, read 150k tokens before the steps that needed it).
- **First run on the split skill** (sailboat, POC 0.26.0, 2026-11-12): sealed on the first try with 2 problems left
  (the earlier run left 3), and the sky ran past the shoreline this time. It found: `photo_prep` was described as a
  sentence in step 0 but the page wants a dict; locking belongs between the review rounds; the plan's `photo` was
  unclear after a canvas fit; text written before step 7 pointed at diagrams the text reviewer couldn't see.
- **Lock patches** (#56, 2026-11-12): the backward pass matched a clean water step's tone to the finish's, which
  includes the sun path's glow from a later step, and left warm bands. Its local shift is now capped.
