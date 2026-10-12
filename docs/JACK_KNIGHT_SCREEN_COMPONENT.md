# JJ Arena: Jack Knight as a Screen Component

## Direction

A graphic for the **actual Home screen**, not a stand-alone generated fantasy illustration. Interpret the court-card Jack as a stylized medieval knight in an editorial woodcut/court-card style. The recognizable details are a period-inspired helmet, a single feather, an armor-and-mantle silhouette, a held sword and a modest J corner marker.

**Not included:** costume designs made of all four card suits, floating suit symbols, slogan or catchphrase, anime-style full-body character, castle backgrounds, image generation outputs, or ornamental text. Historical exactness is not asserted.

## Placement

- Home banner: vector knight built inline in the HTML as an absolute decorative child. It does not change button/navigation positions or the leader statistics.
- Desktop: 190 × 235 CSS pixels on the right half, clipped by the existing hero card. At mid-width, 146 × 181.
- 320px screens: 105 × 130 CSS pixels; 390–760px screens: 124 × 153 pixels near the upper-right, clear of heading/description/actions. The Jack remains inside the existing Home hero.
- Ranking and Ring/Sit&Go gameplay: no knight DOM or rendering. The feature is limited to Home.
- Hero title uses only **JJ Arena**. The description lists factual sections; it does not include a slogan. On small phones the canonical Home action buttons are already hidden by the original mobile design; navigation remains in the mobile dock.
- Only the Home view's entry fade is disabled, to avoid transient low-contrast screenshots/text on medium screens.

## Brand colors

Midnight `#1B2855`, cyan `#27C7D9`, magenta `#CB4295`, parchment `#F4E8BD`, copper/gold `#E5B960`. Distinguishable medieval figure, without printing playing-card pip patterns on costume.

## Engineering contract

- The image is an authored **inline SVG as source code**, not a generated image file.
- `aria-hidden="true"` and `focusable="false"` because it is decorative.
- No font/image downloads, no JavaScript, no keyframe animation, no network request.
- Canonical `materialized_v1244/` is untouched; one build-time injection produces the required HTML and CSS.
- New cache version forces updated clients to fetch the new home assets.
- Regression tests compare non-Home HTML byte-for-byte, verify preexisting CSS remains intact and cap compressed CSS growth; real Chromium screenshots at 320, 390, 760, 1024, and 1440px, including the actual compiled desktop/mobile app shell. Contrast/opacity and figure/text overlaps are checked after layout settling.
- No production deployment until full CI, screenshot review and performance evaluation.

## Scope boundary

This is a screen-ready **first concept** of the Jack, not a fixed/approved final mascot identity. Character shape and color can be refined without touching game state, scoring or seat placement. If the user does not approve the court-card interpretation, keep the PR draft and do not merge.
