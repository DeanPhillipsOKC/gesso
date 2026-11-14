# Step 1: the simplified reference and the finished painting

## 1a. Simplified reference (`00_reference.png`)
The reference is what the painting is made from: fewer shapes, clear values, colors a beginner can mix.
- Try `simplify --strength 2` or `3`, and look at it. If clutter is left, go higher or try `--method meanshift`.
- Start with `--method meanshift --strength 3` for line art or outlines (Kuwahara breaks thin dark lines) and for
  many small bright dots like stars or sparkles (Kuwahara wipes them out).
- Write trials to `<lesson>/trials/` with `--out`, and copy the one you pick to `<lesson>/00_reference.png`.
- Also make `value-study --tones 3` and `palette --colors 6` (with `--lesson`).
- Only if no filter result reads as a clean reference, render it with the technique's `simplify.prompt`
  (`render --step reference --max-cost 0.40`, reason required).

## 1b. Finished painting (`99_finish.png`)
No filter turns a reference into an acrylic painting, so this is a render:

`render --step finish --inputs <reference> <photo> --prompt "<finish.prompt> The second image is the original
photo: take every area's colors from it, and keep each area's share of the canvas (if the water is the bottom
third there, it's the bottom third here). No text, signature, or watermark. <framing>" --quality high --max-cost 0.40
--out <lesson>/99_finish.png`, with a reason.

- Pass the photo too: a reference alone drifts in color. With a beginner version, pass it as the photo, not the
  original, or the original's detail flows back in.
- Every step is cut from the finish, so it gets high quality.
- With `--palette`, name the painter's tube colors in the prompt in place of the technique's five.

Then Read the finish and the photo and compare. Simplifying is expected. Flag only what the owner would notice
and mind:
- an area changed color or hue;
- something was added, removed, or turned into something else;
- a texture changed character;
- the mood or time of day changed;
- the subject looks stretched or squeezed (the frame snaps to 1024x1536, 1536x1024, or 1024x1024, so a slightly
  different shape is fine);
- with a beginner version, anything on your drop or merge list came back.

With a beginner version, also run `busy <lesson>/99_finish.png --lesson <lesson>`: fine texture has to stay below
the photo's (`came_down`). If it didn't, flag it, naming where `busy/99_finish.jpg` outlines it. With no beginner
version, skip this: a calm picture's finish measures a little more than its photo from brush marks, and nothing
compares it.

If anything is flagged, render once more with `--inputs <finish> <photo>` and a prompt listing the fixes
("Repaint it with these fixes so it matches the second image: ... Keep everything else the same"). Save the
flagged list for `review.json` as `finish_issues`. With a beginner version, run `busy` on the new `99_finish.png`
too, so the number recorded is the finish the lesson uses.
