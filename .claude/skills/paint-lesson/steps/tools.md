# Tool order for every image

For each image the lesson needs, take the first of these that does the job, and write down which one and why.
Every filter run with `--lesson` needs `--why` (what you want it to show you) and takes `--step <id>` when it's for
one step. Both go in the ledger, and the page shows them under "How this lesson was made".

1. **A filter** from `tools.py --help` (value study, notan, palette, simplify, posterize, edges, grid, ...).
2. **A composite** from the finish: `from-finish --steps ... --in-place` for a base coat and its texture passes
   (step 6a). Whole-picture compositing isn't ready yet.
3. **A throwaway filter**: a one-off script in `<lesson>/filters/`, 2 tries at most. Write every try's output in
   `<lesson>/filters/`, and copy only the one you use to `<lesson>/NN_<id>.png`. If neither works, keep the better
   one as a seed for option 4, and list each throwaway in your report.
   - Worth trying when a step only takes away things that sit on a simple background (trees in front of a sky).
   - Skip it when a later layer hides something the step has to show (the sky behind vines): inpainting can't
     invent what was covered.
4. **A render seeded by a filter or composite**: `render --step <id> --inputs <seed> --out <lesson>/NN_<id>.png`
   with your own prompt. Start with what the image is ("This is an acrylic painting at the step where ..."), say
   what to fix or remove, say to keep placement, sizes, and colors exactly, and end with the technique's `framing`.
5. **A plain render** (`render` or `render-step`), with `--why-not-filter` saying why 1 to 4 can't do it.

The same render with the same inputs comes back free from the cache, so rerunning to change text costs nothing.
