# JJ Arena Lightweight Editorial UI

Date: 2026-10-11
Status: Draft PR, not a production design approval

## Decision

The redesign should make the product feel like a restrained club/competition
interface, not a generic generated SaaS dashboard. Above all, it must not make
the app heavier. Preserve all Ring and Sit&Go game behavior.

## Phase 1

- Home: flat editorial hero, a compact vertical top-five list, readable session
  and table panels. The current Home elements and IDs must remain unchanged.
- Rankings: preserve filters, player search, podium and all table data, but
  replace promotional gradients and elevated cards with dividers.
- Shared primitives: smaller corner radii, reduced nonessential shadows,
  flat primary buttons, and a solid mobile sticky header.
- No new SVGs, photos, icon frameworks, fonts, JS, or network dependencies.
- Do not edit materialized_v1244. Perform transformations only during the
  deterministic served-asset build; never on each request.

## Acceptance: required before merging

1. Generated stylesheet raw and gzip byte counts must not exceed the
   equivalent generated stylesheet with this transform disabled.
2. Run lightweight editorial smoke tests and all affected browser tests.
   Compare actual final served assets, not only the canonical input.
3. Manually inspect Home/Rankings on narrow phone widths (320-390px), normal
   phones, tablet and desktop. Verify no clipped names or point totals, no
   scrolling traps, no loss of ranking search/filter/podium content and no
   tap targets below 44px.
4. Compare actual cold and warm loads on a production-equivalent deployment:
   mobile p75 LCP <= 2.5s, INP <= 200ms, CLS <= 0.1.
   Also reject any statistically meaningful latency regression against a
   pre-release baseline. A byte-budget pass is NOT proof of Core Web Vitals.
5. Compare poker action latency, hand log, timers, reconnect and Sit&Go
   separately. This redesign must not alter these product paths.
6. Keep changes on a draft PR until CI and browser validation complete.

## Follow-up phases (not part of this PR)

- Poker Lab: editorial diagrams and compact teaching panels.
- Online poker: tournament-broadcast style only if table readability, motion
  cost and action responsiveness remain unchanged or improve.
- Admin: high-density utilitarian tables, focusing on mobile safe areas.
- Remove obsolete declarations rather than layering more overriding CSS.

## Rollback

Revert the editorial transform invocation and asset version change. No DB
migration or application/game logic changes are involved.
