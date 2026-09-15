# Single-table Sit&Go

Initial release: free scheduled 2–6-player freezeout; 10,000 tournament chips,
10-minute blind levels, big-blind ante, no late registration/re-entry/prizes.
The last prepared level repeats until a winner is determined. 90 minutes is a
target, not a forced ending. Ring and tournament chips never share settlement.

The existing ring table renderer, cards, raise sizing, pre-actions and connection
recovery are reused. Tournament actions additionally carry the hand ID; delayed
requests cannot act on the next hand. The lobby provides an explicit table/rejoin
button and recent results. No production event is created by deploying this code.

Tournament conventions reference PokerStars' published rules:
https://www.pokerstars.com/poker/tournaments/rules/
Random seats; advancing button; button is small blind heads-up; simultaneous
eliminations ordered by starting stack, equal stacks tie; disconnected entrants
continue paying blinds, and time out to check/fold. JJ's ante policy explicitly
posts the big blind first, then as much of the ante as the remaining stack allows;
BBA remains in heads-up. Ante is dead money available to all live hands, never
call credit or an uncalled contribution.

The immutable materialized engine is loaded into a separate module namespace.
Tournament-only ante and zero-rake wrappers cannot change ring engine globals.
Tables, complete hands and chat are persisted in sitngo_games / sitngo_hands /
sitngo_messages. They do not enter online_hands, online_hand_results or point_ledger.
The full deck remains server-private. Public live/history payloads use the same
viewer-specific card privacy as ring tables. Results and final status commit
atomically with game state. Optimistic revisions reject stale writers.

The scheduler preserves 45-second action deadlines, staged runouts and at least
1.6 seconds between hands (including the canonical showdown hold). Blind levels
change only when dealing a new hand. Checkpoints are written at every action and
at most five seconds apart during play. Restart resumes the saved hand and moves
deadlines by the time since the last checkpoint; up to five seconds of recent
play can be treated as downtime. It does not redeal or restore spent chips.
Deploy one application worker, as required by the existing in-process ring locks.

Only one new tournament starts while another is running. A due event waits for
that event to finish; the blind clock starts when its actual table is created.
Register after leaving a ring seat; a registered/active tournament reserves table
membership until cancellation/elimination. Existing Phase 1 events marked running
without games resume by creating their first real hand with the assigned seats.

Validation: complete 2/4/6-player tournaments; total-chip conservation; zero cash
ledger effects; short BBA; tied eliminations; restart; timeouts; blind changes;
authenticated HTTP/WebSocket; stale hand and duplicate action handling; cash-only
endpoint rejection; chat/history privacy; phone/desktop ring UI actions.
