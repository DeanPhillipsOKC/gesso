# Step 3: paints

The paints are measured from the finished painting, not chosen by eye. Do this once the outlines are right and
before you write any steps.

1. `paints --lesson <lesson>`. It measures each part's main colors, writes `plan.json`'s `paints` and
   `trials/paints.jpg`. Read the sheet.
   - It aims for the technique's `max_mixes` (10). It never merges two colors a painter could tell apart, so it may
     stop above 10 and print `over_target` saying which colors kept it there. That's allowed. Don't merge by hand.
   - A paint with `"of"` and `"plus"` is a lighter or darker version of another paint ("plus white"). It doesn't
     count as a mix of its own.
   - Each paint lists the `parts` it's for. A paint two parts share was close enough in both to be one mix.
2. Give every paint a `name` and a `used_for`. Nothing else about a paint is yours to change.
   - Name it for what it looks like: "Misty blue-gray", "Bark brown". A paint that two parts share needs a name
     that fits both ("Warm rust", not "Foliage rust", if the bark uses it too).
   - `used_for`: a few words, "the sky's cool edges, the far trunks".

## Later in the run
- **A part needs one more color** (to split a pass in two, or to carry something you dropped in step 2):
  `paints --add <part id>`. It measures one more color for that part and touches nothing else. Name it. If it says
  the part has no other distinct color, the split isn't there to make: use the paints the part has.
- **You changed `parts` and ran `outline` again:** run `paints --lesson <lesson>` again. It keeps every paint a
  step uses, and the names of paints whose color barely moved, and prints what changed. Name anything new.
- Never delete or recolor a paint by hand.
