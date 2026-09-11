# JJ Arena Live v1.4 Test Report

Date: 2026-09-06 (JST)

## Automated suite

- 31/31 pytest tests passed.
- Covers ranking seed, logout/session revocation, approval flow, fixed two-table 6-max configuration, 150bb seating/rebuy, card privacy, out-of-turn rejection, WebSocket cookie auth, hashed sessions, admin hand VOID audit, idle-seat pruning, 10%/5bb-cap rake, side pots, all-ins, and 1bb=3pt settlement.

## Randomized poker-engine stress test

- 5,000 randomly generated 2-6 player hands passed.
- Random starting stacks: 1bb-500bb.
- Random legal fold/check/call/raise/all-in actions.
- Verified every hand terminates.
- Verified no negative stacks.
- Verified total player stacks + rake equals starting chips.
- Verified sum of player hand P/L equals negative rake.
- Verified rake never exceeds 5bb.

## Privacy/security regression tests

- Online results derive points at 3 points per bb.
- Existing online rows are recalculated on startup to the current multiplier.
- Normal admin member list does not return full email addresses.
- Full email reveal requires admin password reauthentication.
- Duplicate signup does not disclose whether an email is already registered.
- New sessions are stored as one-way SHA-256 digests.
- API responses use no-store plus security headers.
- Regular member-facing endpoints do not disclose member/admin email addresses.
- Password hashes are upgraded opportunistically to PBKDF2-HMAC-SHA256 600,000 iterations for passwords meeting the current length policy.

## Static checks

- `python -m py_compile db.py server.py poker_engine.py app.py` passed.
- `node --check static/app.js` passed.
- Previously undeclared poker UI state variables (`tableClock`, `wakeLock`, `wasMyTurn`, `actionBusy`) are now explicitly declared.

## Browser automation limitation

A local Chromium/Playwright run was attempted, but this execution environment blocks Chromium from navigating to loopback URLs with `ERR_BLOCKED_BY_ADMINISTRATOR`. API, engine, syntax, and randomized tests completed; public-URL browser verification should be performed after Render deployment.
