# JJ Arena Graphics-Only Theme (Draft)

Updated 2026-10-11. Following user clarification, this PR is a **color and graphic treatment**, NOT an editorial layout redesign.

## User intent / design decision

- Improve the overall distinctive identity through color, backgrounds, restrained graphic details and consistent brand accents.
- Keep the original screen layout, card arrangement, text sizes, spacing, hit targets, ranking podium order, navigation and all online poker operations intact.
- Preserve Japanese legibility and visual contrast.
- Avoid new image files, external fonts, runtime JavaScript, web requests and heavy blur/animation.

## Trial color direction

- Chalk white: `#F3F1EC`
- Deep maritime blue: `#192D3B` / action teal `#245366`
- Copper: `#996035`; pale copper `#E7C5A1`
- Main text: `#192E3A`; muted text: `#53636C`
- Accent: simple flat-color backgrounds and unobtrusive JJ watermark on home hero.

All color choices are a **reversible proposal**, not yet approved.

## Constraints and verification

1. No change to layout-related CSS declarations, no element order or component logic changes. A stylesheet contract test compares existing and themed Home/Ranking layout selectors.
2. Compare generated CSS (raw/gzip) against the same build with the theme disabled. Require no size increase.
3. Browser checks use Japanese test fonts installed **only on CI runners**; screenshots cover Home/Ranking at widths 320, 360, 390, 760, 1024 and 1440px.
4. Contrast for major text must meet at least 4.5:1. Existing font sizes and tap-target dimensions remain unchanged; pre-existing accessibility issues are out of scope for this purely graphic change.
5. Run existing stability, poker visibility, Sit&Go, points, PWA cache and production release CI tests.
6. Do not release until screenshots are reviewed and the trial palette is accepted; actual production LCP/INP/CLS must still be measured before deployment.

## Rollback

Revert the single build-time theme transformation from `served_assets.py` and the asset version bump. No application logic or database migration.
