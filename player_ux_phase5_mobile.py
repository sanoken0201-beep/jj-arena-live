from __future__ import annotations

"""Mobile compatibility rules for Phase 4B poker ergonomics.

The materialized mobile layout intentionally hides the action bar while the hero
is waiting and clips hand-result banners to a non-interactive toast. Phase 4B
adds waiting pre-actions and an expandable settlement panel, so those two older
mobile rules need narrowly-scoped overrides. The canonical materialized tree
remains immutable.
"""

PHASE5_MOBILE_MARKER = "v2 player-ux phase4b mobile-compat 2026-09-12"

PHASE5_MOBILE_CSS = r'''

/* v2 player-ux phase4b mobile-compat 2026-09-12 */
@media(max-width:760px){
  /* Waiting pre-actions must remain reachable even though the legacy mobile
     layout normally hides #actionBar until it is the hero's turn. :has()
     scopes this override to a seated, eligible waiting player because the
     pre-action markup is not rendered for observers, sit-outs or folded seats. */
  body.jj-mobile-table-open #actionBar:has(.jj-v5-preactions){
    display:block!important;
    position:fixed!important;
    z-index:118!important;
    left:0!important;
    right:0!important;
    bottom:54px!important;
    width:auto!important;
    min-height:0!important;
    max-height:none!important;
    overflow:visible!important;
    margin:0!important;
    padding:5px 7px!important;
    border:1px solid rgba(255,255,255,.08)!important;
    border-bottom:0!important;
    border-radius:15px 15px 0 0!important;
    background:rgba(7,13,11,.985)!important;
    box-shadow:0 -7px 22px rgba(0,0,0,.30)!important;
    backdrop-filter:blur(12px)!important;
    -webkit-backdrop-filter:blur(12px)!important;
  }
  body.jj-mobile-table-open #actionBar:has(.jj-v5-preactions) .jj-v124-waiting{
    min-height:24px!important;
    padding:1px 4px 5px!important;
    margin:0!important;
    font-size:.62rem!important;
  }
  body.jj-mobile-table-open #actionBar:has(.jj-v5-preactions) .jj-v5-preactions{
    padding:5px 4px 3px!important;
    border-top:1px solid rgba(255,255,255,.06)!important;
  }

  /* The legacy mobile result toast is max-height:54px and pointer-events:none.
     Phase 4B needs the initial settlement to be readable and its collapse/
     expand control to remain operable. It auto-compacts after seven seconds or
     as soon as the hero receives the next decision. */
  body.jj-mobile-table-open #resultBanner.result-banner:not(.hidden):not(.jj-v5-result-compact){
    max-height:min(56dvh,380px)!important;
    overflow:auto!important;
    pointer-events:auto!important;
    -webkit-overflow-scrolling:touch;
  }
  body.jj-mobile-table-open #resultBanner.result-banner:not(.hidden).jj-v5-result-compact{
    max-height:none!important;
    overflow:visible!important;
    pointer-events:auto!important;
  }
  body.jj-mobile-table-open #resultBanner.result-banner:not(.hidden) .jj-v5-result-toggle{
    pointer-events:auto!important;
  }
}
'''


def transform_styles(source: str) -> str:
    if PHASE5_MOBILE_MARKER in source:
        return source
    return source.rstrip() + PHASE5_MOBILE_CSS + "\n"


__all__ = ["PHASE5_MOBILE_MARKER", "transform_styles"]
