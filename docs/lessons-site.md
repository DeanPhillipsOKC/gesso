# The lessons site

A small private website of finished lessons, so the owner and their partner can each open the same lesson on a
phone or tablet while painting. Each lesson is one self-contained HTML page (every picture is built in), so later
animations and interactive pieces work like on any web page. No Claude account is needed to view it.

- `site/` in this repo is the whole site: `index.html` (the list), `lessons/<slug>/index.html` and `thumb.jpg`,
  `lessons.json` (the list's data), and `_headers` (keeps it out of search engines).
- Adding a lesson: `publish` it, then `python spike/tools.py site-add --lesson <lesson folder> --slug <name>`, then
  commit and push `site/`. Cloudflare Pages deploys every push to `main`.
- Who can open it is set in Cloudflare Access (below), never in this repo. Don't put anyone's email here.

Live at https://gesso-lessons.pages.dev, deployed from `main`. It's deliberately **not** locked (owner's call,
2026-11-11: it's painting lessons, nothing private), just kept out of search engines. The Access steps below are
only for if that ever changes; Zero Trust asks for a card even on its free plan.

## Versions on the tiles

Each tile's pick list holds every kept run of that picture (the run folders in `output/` named after it), newest
first, with the current one selected. Opening another version opens the lesson exactly as that run made it: its
page is written once to `lessons/<slug>/v/<run time>/` and never rewritten (runs from before self-contained pages
are built from their saved `lesson.json`, nothing rerun). After a new run of a picture that's on the site, run
`python spike/tools.py site-refresh` and commit `site/`. To make a new run the default, `site-add` it.

## Known problems

Every lesson page on the site ends with a Known problems section (the tile links to it with a count):
- problems the run's reviews found and left as they are (`left` in its review), by step;
- GitHub issues whose text names the run's folder (for example `red-sailboat_skill_20261112-100455`), open or fixed.
  Name the run folder in any bug filed about a lesson so it shows up here. The links work only for the owner (the
  repo is private).

`site-refresh` updates the section on every page. It only rewrites the part between `<!--known-problems-->`
markers, so the lesson's pictures and text, and its hands-off seal, are untouched.

## Lesson history

`site/history/` (live at `/history/`, linked from the list's footer) keeps every run of every picture: `publish`
records each publish that changed the pictures or text, with a strip of every step and the version, commit, cost,
redos, review fixes, and check flags. Each run shows the changelog entries since the run before it, which is where
to look when a lesson got worse. Tick two runs to compare them. The full lessons stay local in
`<lesson>/versions/<n>/`.

- Record the owner's opinion of a run: `python spike/tools.py history-rate --run <output folder>[#n] --score 1-5
  --note "<their words>"`.
- Runs made before the history existed: `python spike/tools.py history-backfill` (versions from before stamps are
  guessed from the run's date and marked so).
- The strips show paintings, never the photos. Keep it that way: the site is open.

## One-time setup (owner, about 15 minutes)

These are Cloudflare dashboard steps; the menus may be worded a little differently than this.

**1. The site (Cloudflare Pages)**
1. In dash.cloudflare.com, go to **Workers & Pages**, then **Create**, then the **Pages** tab, then **Connect to Git**.
2. Pick GitHub and the `gesso` repo. If it isn't listed, give Cloudflare access to that private repo when GitHub asks.
3. Project name: `gesso-lessons` (it becomes `gesso-lessons.pages.dev`). Production branch: `main`.
4. Framework preset: **None**. Build command: leave it empty. Build output directory: `site`.
5. **Save and Deploy**. When it finishes, the site is live at the `.pages.dev` address. Don't share it yet: it's
   public until step 2.

**2. Keep it private (Cloudflare Access, free for up to 50 people)**
1. In the dashboard, open **Zero Trust**. The first time, pick a team name and the **Free** plan; Cloudflare may
   ask for a payment method even for the free plan.
2. Go to **Access**, then **Applications**, then **Add an application**, then **Self-hosted**.
3. Application name: `Painting lessons`. Domain: `gesso-lessons.pages.dev`. Add a second one,
   `*.gesso-lessons.pages.dev`, so preview deploys are locked too.
4. Add a policy: Action **Allow**, Include **Emails**, and type your email and your partner's.
5. Login method: **One-time PIN** (the default). Save.
6. Open the site in a private browser window: it should ask for an email and send a code. Enter yours to check.

**3. Share it**
Send your partner the `gesso-lessons.pages.dev` link. She enters her email, gets a code, and she's in. The sign-in
lasts a while (24 hours by default; the application's session duration setting can make it longer).
