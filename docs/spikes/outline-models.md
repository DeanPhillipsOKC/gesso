# Spike: a better outline model for thin and soft parts (#85)

2026-11-14. Follows `outline-probe.md` and `outlines.md`. The code is `spike/experiments/issue85.py`; nothing in
the pipeline changed.

**Answer: swap the local model for a larger one, and ask it for thin parts the right way. Don't add a hosted
model.** The chickadee's branch, the worst outline on the site, comes out clean and in one piece from a larger
local Segment Anything (SAM ViT-L or SAM-HQ ViT-L, about 340 MB, 4 seconds more per picture, free). Half of the gain
is not the model at all: the pipeline never asks the model for a thin part, because the probe of 2026-11-12 asked
with one box around the whole branch and got the background back. Asked limb by limb, with the points the plan
already has, even today's model outlines the mast and the feet better than the color rule does.

Step 5 of the chickadee gate run ("Paint the branch and trunk dark"), built by the real tools with only the
branch's and the feet's outlines swapped:

![Step 5 today, and with the branch outlined by ViT-B, ViT-L and SAM-HQ ViT-L](outline-models-step5.jpg)

## What was run

Nine promptable models and one matting model, all as ONNX files on CPU with `onnxruntime` (no PyTorch), on six
pictures: the three fixtures (1000 x 786) and the three gate runs (1536 x 1024; `chickadee_skill_20261113-041241`,
`red-sailboat_skill_20261113-041240`, `balloon-lavender_skill_20261113-041226`). Prompts came from the plans as
they are: nothing was hand-tuned for a model.

| Model | Files | Once per picture | Per prompt | Same result twice |
|---|---|---|---|---|
| SAM ViT-B, quantized (today's) | 109 MB | 4.1 s | 0.04 s | yes |
| SAM ViT-L, quantized | 341 MB | 8.2 s | 0.04 s | yes |
| SAM ViT-H, quantized | 666 MB | 13.7 s | 0.03 s | yes |
| SAM-HQ ViT-B, quantized encoder | 121 MB | 3.0 s | 0.10 s | yes |
| SAM-HQ ViT-L, quantized encoder | 345 MB | 7.6 s | 0.12 s | yes |
| SAM-HQ ViT-H, quantized encoder | 679 MB | 13.4 s | 0.12 s | yes |
| SAM 2.1 Small | 183 MB | 1.5 s | 0.04 s | yes |
| SAM 2.1 Base+ | 360 MB | 2.6 s | 0.04 s | yes |
| SAM 2.1 Large | 910 MB | 5.9 s | 0.03 s | yes |
| BiRefNet, small (a matting model, no prompts) | 224 MB | 7.1 s per part | | not checked |

Times are on 4 CPU cores, the median over the six pictures. All of it is free. The files come from GitHub
releases: today's model from rembg's, the others from X-AnyLabeling's exports (`CANDIDATES` in the script has
every address). A lesson runs `outline` up to three times, so ViT-L or SAM-HQ ViT-L adds about 12 seconds to a
run of 16 to 20 minutes.

Each part was asked for in up to five ways (`recipes` in the script): one box; the box with the plan's
`points_in` and `points_out`; the points alone; points along a thin part's `paths`; and **per limb**: for each of
a thin part's paths, a box around that path, points along it, and the `points_out` that fall inside the box, with
the limbs' outlines joined, kept inside the band the pipeline already draws around the paths, and pieces under
0.05% of the picture dropped.

There is no hand-drawn outline to score against, so "clean" is by eye, from the pictures below. The script also
counts pieces and overlap with today's outlines (`output/spike85/results.json`); those numbers only back up what
the pictures show.

## What it showed

**The branch.** Top six: the gate run. Bottom six: the fixture.

![The branch, six ways, on both chickadee pictures](outline-models-branch.jpg)

- Today (the color rule): on the gate run, seven pieces, with misty background stuck along the top and the right
  twigs. This is #100's fault. The fixture's branch was tuned by hand over three rounds and is fair.
- One box around the whole branch, the probe's way: SAM and SAM 2.1 return most of the picture at nearly every
  size (63 to 87% of it; the branch is 13%). SAM-HQ returns the branch with background attached, in 3 to 15
  pieces. This is what "the model fails on thin parts" was based on.
- Per limb: ViT-L and SAM-HQ ViT-L return one clean piece on both pictures, twigs and leaf stems included, with
  the feet left out. ViT-B is as clean on the fixture but takes other blobs on the gate run (nine pieces). SAM 2.1
  Large is close to ViT-L; SAM 2.1 Base+ breaks up (15 and 12 pieces); SAM 2.1 Small is fair.
- One fault is left with every model: on the gate run a leaf cut off by the left edge is taken with the branch.
  It sits inside the branch's band and the plan's leaf boxes don't cover it.

**The mast.** Top: the gate run (a mast and a boom). Bottom: the fixture.

![The mast, eight ways, on both sailboats](outline-models-mast.jpg)

Every model, today's included, returns a straight mast of even width. The color rule's mast is ragged, with a
lump at the foot and a boom twice too thick.

**The feet.** Top: the gate run. Bottom: the fixture.

![The feet, six ways](outline-models-feet.jpg)

One box, no points, and every model returns two clean feet, today's included. The color rule's fixture outline
takes a slab of branch under them. The feet never needed the color rule: as an `object` with a box they work with
the pipeline as it is.

**The misty trunks.** Top: the gate run. Bottom: the fixture. Box and points.

![The trunks, eight ways](outline-models-trunks.jpg)

The larger models give smooth-sided trunks where the color rule gives ragged ones and, on the fixture, takes haze
between the trunks. SAM-HQ ViT-L and ViT-H are the cleanest; ViT-B and SAM 2.1 Large are speckled. No model finds
the faintest trunk on the left. This is an improvement, not a fix.

**Paint with no single edge** (clouds, a reflection): the models return one solid shape where the color rule
returns the marks themselves. Neither is wrong; the marks are what the steps paint, so these stay on the color
rule.

![Clouds and a reflection: the color rule keeps the marks, the models return one shape](outline-models-soft.jpg)

**Parts with a clear edge** (the bird, the sails, the trees): every model agrees with today's to within what
later parts take back. A swap doesn't cost the easy parts anything that showed here.

**A matting model can't be asked for a part.** BiRefNet returns "the thing in front" of whatever crop it's given:
the bird when the branch was wanted, the branch when the trunks were, the sail for the mast. Only the feet, alone
in their crop, came back right. Its edges are soft, and that didn't help: a painted edge is hard, and every pixel
has one owner in `parts/owner.png`. A soft edge would mean blending two parts' paint in `build-steps`, for no
visible gain on these pictures. (The full-size BiRefNet, 973 MB, ran out of memory on this machine.)

## Hosted models: looked up, not run

Nothing hosted was called. This session had no key for any provider and couldn't reach them. What follows is from
the providers' pages as a web search returned them on 2026-11-14; the prices disagreed between pages and none was
confirmed on a live pricing page, so treat them as rough.

| What | Where | Price | Notes |
|---|---|---|---|
| SAM 3 and 3.1, text, box or point prompts | fal.ai | about $0.005 to $0.01 a request | hard outlines; no seed or same-result promise found |
| SAM 3, text prompts | Roboflow | well under a cent a picture | hard outlines |
| SAM 3 | Replicate, community copies | about $0.001 to $0.002 a run | could disappear |
| BiRefNet, BRIA RMBG 2.0 (matting) | fal.ai, Replicate, Bria | $0.0004 to $0.03 a picture | no prompts: only "the thing in front" |
| ZIM (matting you can prompt like SAM) | nowhere hosted | | local only, non-commercial licence |

- A lesson would cost about 1 to 5 cents more (one request per part that needs it, up to three outline rounds).
- Nothing published shows SAM 3 doing better than SAM 2.1 on thin things, and SAM 2's own paper lists fine detail
  as a weak point. SAM-HQ is the one with published thin-object results (ThinObject-5K: 89.5 against SAM's 73.6
  mIoU; DIS: 78.6 against 62.0; its paper, arXiv 2306.01567).
- No provider promises the same outline twice. The pipeline's rule is the same bytes for the same input.
- A text prompt ("the branch") would save writing paths and points. That's the one thing a hosted model offers
  that the local ones don't, and it's about the plan's effort, not the outline's quality.

Not reachable from here, so not tried locally either: SAM 3 as ONNX (about 3.6 GB) and ZIM.

## Recommendation

Checked against `docs/decisions.md`: tools over inference (a free local tool), cost never at the expense of
quality (it costs nothing and looks better), the outline model runs only where a lesson is made (still true), and
every tool gives the same output for the same input (true of all nine models).

1. **Swap the local model for SAM-HQ ViT-L.** 345 MB once, 4 seconds more per picture, no cost. SAM ViT-L is as
   good on the branch and the mast; SAM-HQ ViT-L is cleaner on the trunks and has the published thin-object
   results. They're close enough that the build issue should run both on its first real lessons and keep the one
   that does better. ViT-H costs 6 more seconds a picture for nothing that showed. SAM 2.1 is faster but its
   middle size breaks up and its confidence numbers are no use (0.0 to 0.9 on good outlines), which the outline
   checks rely on.
2. **Ask the model for thin parts, per limb**, as above, and keep the color rule as the fallback for a thin part
   the model returns nothing for. This needs the paths and points a plan already has.
3. **Small things with an edge are `object` parts, not `marks`**: the feet, and trunks with a box and points.
   That's a change to the skill's guidance, not to the tools.
4. **Clouds, sun paths, reflections, foliage stay on the color rule.**
5. **No hosted model.** The local swap fixes the fault, costs nothing, and repeats exactly.

For #100: its option 2 (a better outline model) fixes its step 5, so the image-model edit and the re-render
aren't needed for this case.

## What isn't known

- Two scenes have a thin part (one branch, one mast, each in two renders). The per-limb prompt is tuned on those.
- The plans' paths and points were written for the color rule. Whether a hands-off run writes paths good enough
  for the model in two rounds is for the build issue's first real runs to show.
- The left-edge leaf on the gate run, and the faintest trunk, are still wrong with every model.
- The ONNX files are other people's exports of the published weights. The build issue pins each by SHA-256, as
  today's are.
- Hosted prices and behavior are from search results, not from running anything.

## To run it again

```
python spike/experiments/issue85.py fetch     # 4.5 GB into models/spike85/
python spike/experiments/issue85.py run       # about 10 minutes; outlines and numbers in output/spike85/
python spike/experiments/issue85.py sheets    # the pictures on this page
```
