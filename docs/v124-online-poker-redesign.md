# JJ Arena v1.24 online poker redesign

This release makes the final online-poker presentation layer explicit instead of relying on selectors inherited from older mobile patches.

## Presentation invariants

- Hole-card ranks and suits are independent `span` elements and may never be targeted by amount-label selectors.
- Server `call_amount` is a raw-chip value; UI amounts convert it through the table big blind before display.
- Desktop hole cards render above informational bet markers, and desktop bet markers use separate visual lanes.
- The decision console has one information row, one sizing row, and one primary-action row.
- Primary actions divide the available width equally for one, two, three, or four decisions.
- A stack-consuming call is rendered once as an all-in call, not as duplicate Call and All-in decisions.
- Stack and effective-stack summaries use whole-BB ceiling display; transactional chip accounting remains exact.
- Bet/raise number controls keep the `BB` unit horizontal and non-wrapping.
- Mobile retains the validated portrait geometry, safe-area behavior, two-tap all-in protection, disabled-action explanations, action clock, reconnect state, sounds/haptics, and duplicate-action idempotency.

## Release gates

The v1.24 CI suite reconstructs the exact production runtime and checks JavaScript syntax, engine regressions, PostgreSQL concurrency, WebSocket security, card privacy, prior release regressions, and terminology. It also launches headless Chromium at 1440x900 and 390x844 to assert that the action console does not overflow, primary actions remain equal-width, `BB` stays horizontal, card ranks remain visible, and desktop hero cards do not intersect the hero bet marker.
