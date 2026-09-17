# Single-table Sit&Go

Sit&Go is a scheduled 2–6-player tournament. New events default to 30,000 tournament
chips, 10-minute levels, big-blind ante and a 150-minute prepared structure, but the
administrator owns the event configuration: starting stack, SB, BB, BBA, each
level duration, post-start registration window and per-player re-entry cap can be
edited before the event starts. Once play begins the saved configuration is locked.
The default remains a freezeout: post-start registration is 0 minutes and re-entry
is 0. The last prepared level repeats until a winner is determined. 90 minutes is
a target, not a forced ending. Ring and tournament chips never share settlement.

The existing ring table renderer, cards, raise sizing, pre-actions and connection
recovery are reused. Tournament actions additionally carry the hand ID; delayed
requests cannot act on the next hand. The lobby provides an explicit table/rejoin
button and recent results. No production event is created by deploying this code.

## Entry policy

An administrator may configure `late_registration_minutes` from 0 to 60. A value
of 0 closes registration at the scheduled start. A positive value allows a new
unique player to take an unused seat until the actual tournament start time plus
the configured number of minutes. The unique participant count never exceeds six.
A late-registration request received during a live hand is stored as pending and
the player is seated only between hands. Joining never restarts the blind clock.

`max_reentries` is 0 to 5 per player and may be positive only when a post-start
registration window exists. Re-entry is offered only after that player's stack has
reached zero and the elimination has been committed. The player receives exactly
the event's configured starting stack, returns to the same seat, and re-enters only
between hands. Re-entry increments total entries but not the six-player unique-field
limit. Previous elimination data for that player is removed and final places are
renumbered when the field changes.

Late registration never keeps an otherwise finished Sit&Go alive merely because an
unused seat remains. A player whose late-registration request was already accepted
before the terminal hand is still seated between hands and prevents premature
finalization. If a heads-up bust would otherwise end the tournament while that
newly busted player is still eligible for re-entry, the table pauses for up to
30 seconds (never beyond the configured entry deadline) so that player may choose
to re-enter. Older unused re-entry rights do not indefinitely delay a one-survivor
finish. Pending tournament entry reserves table membership so the same user cannot
simultaneously join a ring table.

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
Register after leaving a ring seat; registered, active and pending tournament
entries reserve table membership until cancellation/elimination as applicable.
Existing Phase 1 events marked running without games resume by creating their
first real hand with the assigned seats.

Validation covers complete 2/4/6-player tournaments; default freezeout behavior;
late registration; re-entry caps; terminal-HU re-entry grace; accepted pending
entry activation; entry-clock preservation; final-place renumbering; total-chip
conservation; zero cash-ledger effects; short BBA; split/odd chips; main/side pots;
BBA main-pot integration; denomination-aware raises; scheduled and custom color-ups;
micro-stack survival; restart; timeouts; blind changes; authenticated HTTP/WebSocket;
stale hand and duplicate action handling; cash-only endpoint rejection; chat/history
privacy; and phone/desktop ring UI actions.
