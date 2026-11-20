# The gate lessons' chains, kept for #289

`output/` isn't in the repo, so each picture's `chain/` here holds what a spike on the step pictures needs from the
lesson folder named in `RUN`, copied on 2026-11-20:

- `P<nn>.jpg`: the picture at the end of unit nn (`chain/P<nn>.png`, saved as JPEG at quality 92, full size);
- `masks.npz`: `v3/masks.npz` as it was (`s<nn>` each unit's shape, `m<nn>` where each step lays paint);
- `owner.png`: `parts/owner.png` as it was (which unit owns each pixel at the finish).

The units are `plan3.units` of `data/plan.json`. The pictures are JPEGs, so compare them with a threshold
(`erase3.WEAK`), never pixel for pixel.
