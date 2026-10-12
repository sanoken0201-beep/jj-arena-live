# JJ Daily Quiz: static 300-question audit (2026-10-12)

## Scope

The static question bank contains **300 questions**, split equally into the following categories (30 each):
`pot_odds`, `equity`, `mdf`, `spr`, `combo`, `vocabulary`, `icm`,
`bet_sizing`, `range`, `hand_reasoning`.

Provenance: **160 original questions + 40 Japanese-reviewed additions + 30 intermediate GTO-blog-based additions + 70 further authored questions = 300**.

**Not included**: administrator-custom or GPT-generated questions in the production
`quiz_custom_questions` database table. Those require a separate authenticated
export and content audit. An audit of this static source must not be described
as proof that private administrator content is correct.

## Checks against every one of the 300 questions

The production release gate executes `smoke_test_quiz_full_audit.py` in addition
to `smoke_test_daily_quiz.py`:

- Unique question keys and original Japanese prompts; 30 items per category.
- Exactly one correct answer and four distinct choices, *both before and after*
  the real `make_readable()` transformations.
- Answer label presence; nonempty prompts/explanations; display prompt length
  capped at 250 characters; correct human-readable category labels.
- No unresolved glossary abbreviations or identified unnatural automatic
  replacements in question stems.
- Correct dated 30-day one-pass rotation per category, 10 questions per day;
  repeat generation remains deterministic.
- All **31 parameterized legacy numerical questions** are independently
  recalculated from their keys (pot odds, pure-bluff break-even, MDF, SPR,
  call/fold indifference).
- Authored arithmetic spot checks include 3-way ICM payout, weighted combo
  arithmetic, suited/off-suit card removal, call pot odds and rake,
  geometric bet sizing, multi-street bluff EV, tie equity and EQR.
- Exactly 100 newly source-backed questions have mapped reference titles and
  GTO Wizard article URLs. The authoring links are exposed after answers only.
  Blog references establish conceptual provenance; example calculations and
  assumptions are self-contained and have their own validation.
- Prior user answers, scoring rules (correct +10pt, wrong +5pt), and existing
  day-level persisted question sets are untouched.

## Editorial issues found and corrected

| Area | Finding | Resolution |
|---|---|---|
| Japanese SPR numeric display | ASCII `です.` was mixed into Japanese | Use `です。` |
| Vocabulary | Repeated definitions of range advantage, nut advantage, blockers, unblockers and geometric bets | Replace 5 redundant questions with distinct backdoor draws, equity denial, showdown value, merged value betting, and monotone-board terminology |
| Equity | Win 30%, tie 20%, lose 50% appeared twice | Replace one with a new independent win/tie calculation |
| ICM | “Positive chipEV but negative prizeEV” duplicated the same conceptual item | Replace with a 3-player ICM payout calculation explicitly showing conditional runner-up probabilities |
| Combos | Basic 6-combo pocket-pair calculation duplicated existing material | Replace with suited-removal-aware AKo combination counting |
| Range | Multiple questions repeated the bluff disadvantage of blocking folds | Replace one with a check-frequency Bayesian range update |
| Cold call terminology | Unqualified “haven't put in chips” potentially excluded posted blinds | Specify no *voluntary* pre-existing chip contribution |
| Monotone sources | Generic poker-equity article didn't directly document the board term | Cite the verified GTO Wizard monotone-flop article |

Repeated **parameterized numerical exercises** with different pots, stacks or
frequencies are retained intentionally: those test consistent use of the
formula rather than duplicating the same wording and answer.

## Independent reference reading

- [MDF & Alpha](https://blog.gtowizard.com/mdf-alpha/) — limits and formula for pure-bluff/MDF calculations.
- [Mathematical Misconceptions in Poker](https://blog.gtowizard.com/mathematical-misconceptions-in-poker/) — distinction between pot odds, equity and EV.
- [Equity Realization](https://blog.gtowizard.com/equity-realization/) — EQR and strategy context.
- [Pot Geometry](https://blog.gtowizard.com/pot-geometry/) — geometric bet sizing and idealized assumptions.
- [The Mechanics of C-Bet Sizing](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/) — range/nut advantage and sizes.
- [Blockers & Unblockers](https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/) — selecting bluffs.
- [What is the Bubble Factor?](https://blog.gtowizard.com/what-is-the-bubble-factor-in-poker-tournaments/) — tournament-risk modeling.
- [Maximizing Value on Monotone Flops](https://blog.gtowizard.com/maximizing-value-on-monotone-flops/) — monotone-flop definition.

The other verified article links are maintained in `quiz_advanced_bank.SOURCES`.

## Limits and next review trigger

The automated bank audit catches structural regressions, numerical mistakes
in parameterized questions, and the specific high-risk arithmetic concepts
listed above. No finite automated validator establishes the solver-optimality
of every hypothetical poker spot. Broad strategy questions must be read as
**conditional heuristics**, not unconditional solver outputs. The admin quiz
statistics endpoint can be used to prioritize questions with anomalously high
or low response accuracy as real responses accumulate.

If a question changes, do **not** mutate already persisted daily quiz sets,
user answers, or point ledger records. The revised bank applies only to
future newly created sets.
