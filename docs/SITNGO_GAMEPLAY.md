# Single-table Sit&Go

Sit&Go is a scheduled 2–6-player freezeout. New events default to 30,000 tournament
chips, 10-minute levels, big-blind ante and a 150-minute prepared structure, but the
administrator owns the event configuration: starting stack, SB, BB, BBA and each
level duration can be edited before the event starts. Once play begins the saved
configuration is locked. There is no late registration or re-entry. The last
prepared level repeats until a winner is determined. 90 minutes is a target, not a
forced ending. Ring and tournament chips never share settlement.

The existing ring table renderer, cards, raise sizing, pre-actions and connection
recovery are reused. Tournament actions additionally carry the hand ID; delayed
requests cannot act on the next hand. The lobby provides an explicit table/rejoin
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

Random seats; advancing button; button is small blind heads-up; simultaneous
eliminations are ordered by starting stack and equal stacks tie; disconnected
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
1.6 seconds between hands (including the canonical showdown hold). Blind levels
change only when dealing a new hand. Checkpoints are written at every action and
at most five seconds apart during play. Restart resumes the saved hand and moves
deadlines by the time since the last checkpoint; up to five seconds of recent
play can be treated as downtime. It does not redeal or restore spent chips.
Deploy one application worker, as required by the existing in-process ring locks.

Only one new tournament starts while another is running. A due event waits for
that event to finish; the blind clock starts when its actual table is created.
Register after leaving a ring seat. Registration itself is the tournament seating
commitment: a registered/active tournament reserves table membership until
cancellation/elimination, and the player does not need to reconnect or open the
table at start. Every registered entrant is dealt into the tournament and posts
SB/BB/BBA as scheduled while absent; unattended actions time out to check/fold.
Existing Phase 1 events marked running without games resume by creating their first
real hand with the assigned seats.

Validation covers complete free 2/4/6-player tournaments and paid 2/3/4/5/6-player
tournaments; total-chip conservation; exact entry escrow and prize-ledger
conservation; the default six-player 70/30 award; short BBA; split/odd chips;
main/side pots; BBA main-pot integration; denomination-aware raises; scheduled and
custom color-ups; micro-stack survival; restart; timeouts; blind changes;
authenticated HTTP/WebSocket; stale hand and duplicate action handling; cash-only
endpoint rejection; chat/history privacy; and phone/desktop ring UI actions.

## Point entry and administrator-defined prizes

New events accept `entry_fee` (0–1,000,000 pt, two decimal places) and
`payout_percentages`, keyed by actual entrant counts `2` through `6`. Each
array contains one percentage per place and must total exactly 100%; 0% is
valid for any place. Defaults are winner-takes-all for 2–5 players and 70/30
for 6 players, and administrators can replace every percentage.

Registration debits the current season balance even when that balance is below
the entry fee; the official point balance may therefore become negative.
Cancellation before the start, administrator cancellation, and minimum-player
cancellation refund the recorded entry. The first registration locks point terms,
including after cancellation, so published terms cannot change beneath
participants. Existing events with no terms remain free.

Ledger changes share the registration/game transaction. Account/event locks,
a recorded escrow payment, and a unique settlement prevent duplicate charges,
refunds, and awards. Completed-game persistence and prizes commit together.
Integer hundredths preserve the entire pool; largest fractional remainders
receive residual cents in place order. Tied places split the sum of occupied
prize slots, with any indivisible residual cent assigned by randomized seat
order (user ID is only a deterministic fallback). Tournament chips and ring
settlement remain separate. The general manual reversal endpoint cannot reverse
tournament entries independently.

Immediately before the first hand, the service revalidates the persisted payout
configuration and requires the registered field to match unrefunded escrow exactly.
Each paid escrow row must match the locked fee and reference the corresponding
`sitngo_entry` ledger debit for the same user and amount; a free event must have
no active escrow. Any mismatch fails closed before table creation.
