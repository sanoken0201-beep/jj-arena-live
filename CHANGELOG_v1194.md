# JJ Arena v1.19.4

UI foundation release for both player and administrator surfaces.

## Player site
- Add visible keyboard focus treatment.
- Enforce practical mobile touch targets and 16px mobile form controls.
- Respect reduced-motion preferences.
- Add an offline-only connection warning.
- Improve ARIA semantics for toast, login help, poker actions, and quiz choices.
- Harden external blank-target links with `noopener noreferrer`.
- Improve small-screen dialog scrolling.

## Administrator site
- Add visible account-result count and one-tap search clear.
- Add a mobile link back to JJ Arena.
- Add sticky account table headers.
- Localize core account-table headings and ACTIVE state.
- Restore focus to the originating account-management button when a dialog closes.
- Visually separate destructive/session-security actions from ordinary account editing.
- Add the same focus, touch-target, reduced-motion, and mobile-input baseline.

## Non-goals
No ranking calculation, points, account lifecycle, PIN hashing/authentication semantics, tournament stack values, poker engine rules, or hand state are changed.
