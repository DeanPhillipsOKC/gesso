# v4 cost: a cheaper Claude setting for the chain's checker (#268)

C2 of `docs/design/pipeline-v4-plan.md`, under #240, Claude only. Run on 2026-11-20. The code is
`spike/experiments/v4_checker_cost.py`, and its test is in `spike/tests/test_v4_loop.py` (`CheckerCostTests`). Every
answer, with its cost, time and tokens, is in `spike/experiments/v4_checker_cost.json`. The rounds it replays are in
`output/bench/v4-checker/`.

**Verdict: drop. Keep Opus 5.5 at medium effort for the chain's checker** (the owner's call, 2026-11-20: "Default."). No cheaper setting
passes the issue's rule: miss no stray or left-standing piece that Opus catches. Every one missed 4 to 7 of the
29 marks most of Opus's reads made, and at least one of the 25 marks all of Opus's reads made. The closest was
Sonnet 5.5 at medium effort. It caught 24 of those 25, about as often as a second Opus read does (95%). But it
missed 5 of the 29 where Opus missed about 2, and it made 5 marks no Opus read made. It would save about $0.15 a
lesson, 5% of the $3.06. A miss means a thing left in a step picture where it doesn't belong, the kind of fault the
owner found in the cat (#262). That costs more than $0.15.

## What was run

No new renders. Every loop run keeps each render it made, and its state keeps the again-list after every erase. So
each round of the chain's checker can be laid again exactly as the checker saw it: `erase3.run` with that round's
again-list, and a renderer that hands back the saved answer from the render cache.

- **The bench:** the 15 v4 loop runs from #253 and #267 on the cow, the cat and the birch grove. Two were left out
  because a merge `check` asked for came after the checker and changed the plan's units. The other 13 gave
  **23 rounds and 302 looks**. Each run's last round, laid again, matches the run's own looks pixel for pixel.
- **The reference:** the loop's own answer plus two more Opus-at-medium reads of each round. A mark counts when two
  of the three reads made it: **29 marks** (25 left, 4 stray). **25** were made by all three.
- **The settings:** Opus 5.5 at low, Sonnet 5.5 at medium and low, Haiku 5.5 at medium (its default) and high, one
  read a round each. Each gets the loop's message word for word (`chain-check.md`, `asked.json`, every look),
  sent once and uncached, as the API would send it (#253's cut 2).
- **The owner's answers:** none exist for these looks, so the reference is Opus's.

## Results

"Caught" is against the 29 marks two of the three Opus reads made. "All three" is against the 25 every Opus read
made. "Added" is a mark the reference doesn't have, which means a redo render. A lesson averages 1.77 rounds.

| Setting | Caught (of 29) | All three (of 25) | Added (23 rounds) | Marks no Opus read made | A call | A lesson | Seconds a lesson |
|---|---|---|---|---|---|---|---|
| Opus medium, the loop's own read | 27 | | 7 | | | | |
| Opus medium, each repeat read | 28 a read, on average | | 2 a read | | $0.165 | **$0.29** | 46 |
| Opus low | 25 | 23 | 3 | 2 | $0.140 | $0.25 | 22 |
| Sonnet medium | 24 | 24 | 7 | 5 | $0.079 | $0.14 | 31 |
| Sonnet low | 22 | 20 | 6 | 3 | $0.078 | $0.14 | 29 |
| Haiku medium | 23 | 21 | 4 | 2 | $0.009 | $0.016 | 105 |
| Haiku high | 22 | 22 | 12 | 11 | $0.015 | $0.027 | 202 |

**Opus against itself.** A single Opus read caught 75 of the 79 marks both of the other two reads made (95%). Over
its 69 reads it made 11 marks neither other read made. That is the floor a cheaper setting is measured against: the
loop's own checker isn't the truth either.

**What the misses were.** Almost all were `left`, the unit's thing still partly standing. The birch grove's
misty far trunks and pines (`birch-grove_v4loop_20261119-175914`, units 2, 3, 4 and 16) were missed by every
cheaper setting at least once. These are faint, pale things on a pale ground, the hardest looks on the bench. Sonnet
medium's one miss on a mark all three reads made was the cow's nose still under the fringe
(`highland-cow_v4loop_20261119-191115`, U11). Haiku missed the cow's gold cloud streaks and two of the cat's strays
(both at the window).

**Cost.** A call is about 30,000 tokens in, nearly all pictures, at every setting. On Opus the input is most of the
price ($0.12 of $0.165), so low effort saves only $0.025 a call. It writes about 940 output tokens, not 2,200. Sonnet
halves the input's rate. Haiku is 18 times cheaper, but it thinks for 12,000 to 24,000 tokens and takes one to two
minutes a call.

**What a wrong answer costs.** An added mark is one redo render (about $0.02 at low quality) and another checker
round. A miss is a thing left in the step picture before it's painted, or gone too early. No redo comes after it,
because the next round only runs when something is marked. Haiku high's 12 added marks are about one extra render a
lesson. The cheaper settings miss 0.3 to 0.55 marks a lesson, against 0.15 for the loop's own Opus read.

## Out of scope, or left for later

- **The feedback rounds** go back to the stage's writer in its own conversation. That writer is C3's (#267, the lean
  words), not a yes/no helper, so it wasn't tried here.
- **Steps 0 and 1's checks** (the photo check, the finish check, $0.35 a lesson with what else they do) are also yes
  or no. They aren't in v4_loop's checker and weren't tried. Their pictures are few, so Opus low would save little,
  and they decide whether a lesson is made at all.
- **The graders' A/B** wasn't run. No setting passed the miss rule, so no lesson was made with one.
- **If the checker comes back to cost:** Sonnet medium is the one to try, on a larger bench with the owner's
  answers on the birch grove's faint looks. Sending smaller looks is the other lever, since pictures are most
  of the price (#267's lean words did that for the writers).

## Found on the way

- **A capped redo overwrites a run's renders.** When the cost cap stops a redo partway through, the units it had
  already rendered again are saved under the same names (`U<nn>_raw.png`). So the folder no longer holds what the
  checker saw. Four runs were like this. The render cache, keyed by the picture as sent and the request, still held
  the earlier answers, and the replay reads from it first.
- **Haiku 5.5's rates** are in `v4_loop.RATES`: $0.10 in and $0.50 out (prompts under 100,000 tokens), with the
  same cache multiples as the other models.

The spike's calls cost $14.98 of Claude at the API's rates ($11 of it the Opus reads), and no renders.
