# Step 3: paints

The paints are measured from the finished painting, not chosen by eye.

1. `paints --lesson <lesson>`. It writes `plan.json`'s `paints` and `trials/paints.jpg`. Read the sheet.
   - It aims for the technique's `max_mixes` (10). It never merges two colors a painter could tell apart, so it may
     stop above 10 and print `over_target` saying which colors kept it there. That's allowed. Don't merge by hand.
   - A paint with `"of"` and `"plus"` is a lighter or darker version of another paint ("plus white"). It doesn't
     count as a mix of its own.
2. Give every paint a `name` and a `used_for`. Nothing else about a paint is yours to change.
   - Name it for what it looks like and where it's used: "Misty blue-gray", "Bark brown". A paint that two parts
     share needs a name that fits both.
   - `used_for`: a few words, "the sky's cool edges, the far trunks".
3. Record anything odd in `notes.json` (`learned`): a color you expected that isn't there, a merge that surprised
   you.

If you change `parts` later and run `outline` again, run `paints` again too: it keeps the names of paints whose
color barely moved.
