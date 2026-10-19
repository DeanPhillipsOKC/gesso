# Gesso: vision

*From blank canvas to finished painting, one step at a time.*

Gesso turns a photo into a step-by-step painting lesson at your skill level, in acrylic or
oil. Each step shows what your canvas should look like when you finish it, and tells you how to
get there: what to mix, which brush to use, and what to watch out for.

## The name

Gesso is the primer that goes on a canvas before any paint. It's step zero, which fits an app
where real technique comes first and the image generation follows it.

## Why

It's built for two beginners who paint together. Tutorials are great until you want to paint your
own photo, and then you're on your own. Image generators can turn a photo into a painting, but
they jump straight to the finished result and skip everything a beginner needs to see: the sketch,
the underpainting, the blocked-in shapes, and the layers that come after.

## What makes it different

**Real technique drives the pictures.** Gesso doesn't ask an image model to "show the steps."
It first plans the painting the way a teacher would, using the techniques that fit the medium and
the painter's level, and then generates each stage from that plan. The pictures follow the lesson,
not the other way around.

## How it works

1. **You give it:** a photo, a medium (acrylic or oil), a technique (see below), a skill level,
   and optionally a canvas size and how much time you have.
2. **The technique library sets the stages.** Gesso ships with a hand-checked library of real
   techniques for each medium and level: the stages in order, what the canvas looks like at each
   one, brushes, drying times, and common mistakes. No AI invents the steps.
3. **Claude reads the photo, once.** One vision call fills in what a template can't know: the
   subject and focal point, the main shapes, the light and value structure, the palette and the
   mixes for this photo, and one or two photo-specific sentences for each stage. It comes back as
   structured output that slots into the template.
4. **It paints the finish first.** It generates the final painting in the chosen medium, technique,
   and level, so every stage has the same destination.
5. **It works toward the finish.** Each stage image is made by editing the previous stage. The
   image prompt comes from the library's description of that stage, plus Claude's specifics.
   Working this way keeps the stages consistent, so step 5 doesn't turn into a different painting
   than step 2.
6. **It checks its own work (later).** Claude compares each stage image against the plan ("is this
   still a loose value sketch, or did it jump ahead to detail?") and regenerates any stage that
   fails. Optional at first.
7. **You get a lesson** you can follow at the easel, one step at a time.

It will be slow, maybe several minutes per lesson. That's fine. It shows progress as stages
finish, and a finished lesson is saved so it never has to be made twice.

## What each step includes

- The image of the canvas at the end of the step, next to the reference photo
- What to do, in plain words, in the order to do it
- The colors to mix, starting from a small beginner palette, with rough ratios
- Brush type and size, and how to hold or load it when it matters
- How long to let it dry (acrylic: minutes; oil: depends on the layer, see fat over lean)
- Common beginner mistakes at this step, and how to fix them

## Techniques

The library holds techniques per medium, and the painter picks one. A starting set:

- **Acrylic:** block-in and layer (the default for beginners), glazing, dry brush, impasto.
- **Oil:** alla prima (wet into wet, one session), indirect painting over a grisaille or a
  colored underpainting, and glazing.

Each technique lists which levels it suits. The library is plain data in the repo, versioned and
reviewed like code, so improving a lesson means editing a file, not rewriting a prompt.

## Skill levels

| Level | Steps | What changes |
|---|---|---|
| Beginner | 5 to 7 | Simplified shapes, a limited palette (a warm and cool of each primary plus white), larger brushes, forgiving techniques, details left out |
| Intermediate | 7 to 10 | More color mixing, edges (hard versus soft), glazing or scumbling where it helps |
| Advanced | 10 or more | Full value control, color temperature shifts, texture and brushwork, fine detail |

## Mediums

- **Acrylic:** dries in minutes, so layers build quickly. Lessons favor working thin to thick,
  blocking in fast, and fixing mistakes by painting over them. Blending is done quickly or with
  a retarder, so lessons call that out.
- **Oil:** stays wet for days, which allows blending and wet-into-wet work. Lessons follow fat
  over lean (thin, lean layers first, oilier layers on top), include a thin underpainting, and
  give realistic drying times between sessions.

## Models

- **The technique library** (data, no AI) decides the stages and most of each step's text.
- **Claude** makes one vision call per lesson to fill in the photo-specific parts as structured
  output, and later checks stage images. Text inference earns its keep there: a template can say
  "block in the large shapes," but only a model that sees the photo can say "mix ultramarine, a
  touch of burnt sienna, and white for the barn's shadow side."
- **OpenAI's image model** (the gpt-image family, through the API) generates the finish and edits
  each stage. In the owner's own use it has been better at careful, step-by-step image edits
  than Gemini's image model. Keep the image provider behind one small interface so it can change.

## Quality and cost

- A small set of reference photos with expected lesson shapes, run as checks whenever prompts or
  models change, so quality doesn't drift unnoticed.
- Track the cost and time of every lesson (Claude tokens and image calls) and show it in the app.
- Cache everything: the plan, every stage image, and every check result.

## Platform (proposed)

- A web app that works well on a phone, since it'll be used at the easel. Installable like
  RepBunny.
- Vue 3 and TypeScript on the front end, to match RepBunny.
- A small serverless back end that holds the API keys and runs the slow generation work, since
  keys can't live in the browser. Cloudflare Workers is the first candidate.

Decide this in a short spike before building the app. The first milestone doesn't need a UI.

## Privacy

Photos are personal. They stay private to the person who uploaded them: no public gallery, no
sharing by default, and an easy way to delete a lesson and its images.

## How it gets built

The same way as RepBunny: as much of the work automated as possible, built up one piece at a
time.

- The backlog lives in GitHub Issues, scored with effort and value labels (see `docs/backlog.md`).
- Product decisions get recorded in `docs/decisions.md` so agents don't relitigate them.
- **Skills come first.** Start with the two that make everything else work, adapted from
  RepBunny's: `refine-backlog` (turn a rough idea into a scored, buildable issue) and `next-item`
  (pick the best issue, build it, test it, ship it).
- Scheduled routines, review agents, and the rest of RepBunny's automation come later, only once
  the skills have proven themselves here.

## Milestones

1. **Scaffolding:** this doc, the backlog conventions, labels, and the first two skills.
2. **Pipeline spike (no UI):** a script that takes a photo, a medium, and a level and writes the
   plan, the finish, and the stage images to a folder. The goal is to prove the stages stay
   consistent and look like real painting stages. If they don't, rethink before building more.
3. **Web app, minimum version:** upload, choose options, watch it generate, follow the lesson
   step by step on a phone.
4. **Make it useful at the easel:** save lessons, a step timer and drying timer, a "show me this
   step bigger" view, and printing a lesson.

## Not in the first version

- Accounts and sharing
- Watercolor, gouache, pastel, or digital painting
- Video or animated stages
- Selling or recommending paint products

## Open questions

- How many stage images can be generated before cost or time gets silly?
- Should the finish come first (consistent stages) or last (each stage builds naturally)? The
  spike should try both.
- Does the app need the canvas size and shape, or can it crop the photo to a standard ratio?
- Should a lesson suggest simplifying the photo first (cropping, removing clutter) for beginners?
