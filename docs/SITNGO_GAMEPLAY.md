# Single-table Sit&Go

Sit&Go is a scheduled 2–6-player freezeout. New events default to 30,000 tournament
chips and big-blind ante. The administrator owns the event configuration: starting
stack, SB, BB and BBA can be edited before the event starts. New tournaments advance
one blind level after every 12 completed hands; the persisted minute fields are
legacy/rollback metadata and do not select blinds. Once play begins the saved
configuration is locked. There is no late registration or re-entry. The last
prepared level repeats until a winner is determined. 90 minutes is a target, not a
forced ending. Ring and tournament chips never share settlement.

The existing ring table renderer, cards, raise sizing, pre-actions and connection
recovery are reused. Tournament actions additionally carry action, hand and turn
identifiers; delayed or duplicated requests cannot act on a later turn or hand. The lobby provides an explicit table/rejoin
button and recent results. No production event is created by deploying this code.

## Tournament chip rules

100 is the absolute minimum tournament denomination. Every configured stack,
SB, BB and BBA is stored in 100-point units. The active denomination is derived
from the starting stack and all forced bets that remain in the saved structure.
For the default 30,000 structure the scheduled units are:

- Lv.1–4: 100
- Lv.5–6: 500
- Lv.7–10: 1,000
- Lv.11–13: 5,000
- Lv.14 onward: 10,000

A color-up is executed only between hands, immediately before the first hand of a
level that permits a larger unit. It preserves the exact tournament chip supply,
removes obsolete denominations and cannot reduce a live player to zero. Because
this is an online table, the remainder conversion is deterministic rather than a
physical random chip race; the allocation is bounded to whole new chips and is
audited in `tournament.chip_up_history`.

Normal bets/raises must be exact multiples of the active denomination. Calls and
all-ins remain legal through the canonical betting engine, but all tournament
stacks/contributions are checked server-side after every action and before every
save. A state containing a 50-point/1-point chip when the active denomination is
100 or more fails closed instead of being persisted.

At showdown each main/side pot is split independently in whole active chips. The
engine never creates a half-chip. Any odd chip is awarded beginning with the first
eligible tied winner to the left of the button. The BBA is dead money in the main
pot rather than a separate logical pot, so one showdown cannot accidentally make
an additional odd-chip decision just for the ante. Player POT and percentage-bet
UI also includes the posted BBA and uses the active denomination as its sizing
step.

## Tournament conventions

Random seats; dead-button movement; button is small blind heads-up; simultaneous
eliminations use the TDA 2026 BBA post-ante comparison stack and equal stacks tie; disconnected
entrants continue paying blinds, and time out to check/fold. JJ's ante policy posts
the big blind first, then as much of the ante as the remaining stack allows; BBA
remains in heads-up. Ante is dead money available to all live hands, never call
credit or an uncalled contribution. Blind-level changes and color-ups apply only
when dealing the next hand, never in the middle of an active hand.

The immutable materialized engine is loaded into a separate module namespace.
Tournament-only ante, denomination and zero-rake wrappers cannot change ring
engine globals. Tables, complete hands and chat are persisted in `sitngo_games`,
`sitngo_hands` and `sitngo_messages`. They do not enter `online_hands`,
`online_hand_results` or the cash-game point settlement. The full deck remains
server-private. Public live/history payloads use the same viewer-specific card
privacy as ring tables. Results and final status commit atomically with game
state. Optimistic revisions reject stale writers.

The scheduler preserves 45-second action deadlines, staged runouts and at least
1.6 seconds between hands (including the canonical showdown hold). New tournaments
change blind levels only between hands, after each block of 12 completed hands.
Checkpoints are written at every action and at most five seconds apart during play.
Restart resumes the saved hand and moves
deadlines by the time since the last checkpoint; up to five seconds of recent
play can be treated as downtime. It does not redeal or restore spent chips.
Deploy one application worker, as required by the existing in-process ring locks.

Only one new tournament starts while another is running. A due event moves to the
explicit `starting` wait state and starts after the running event finishes; its
tournament clock starts when its actual table is created. While one event is running,
the player lobby also exposes the next scheduled/registration event so its受付 window
is not hidden. Register after leaving a ring seat; a registered/active tournament
reserves table membership until cancellation/elimination. Existing Phase 1 events marked running
without games resume by creating their first real hand with the assigned seats.

Validation covers complete 2/4/6-player tournaments; total-chip conservation;
zero cash-ledger effects; short BBA; split/odd chips; main/side pots; BBA main-pot
integration; denomination-aware raises; scheduled and custom color-ups; micro-stack
survival; restart; timeouts; blind changes; authenticated HTTP/WebSocket; stale
hand and duplicate action handling; cash-only endpoint rejection; chat/history
privacy; and phone/desktop ring UI actions.
