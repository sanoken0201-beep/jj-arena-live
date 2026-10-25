"""Shared illustrated-classic identity for the non-gameplay JJ Arena UI.

All motifs are text/CSS: no images, fonts, scripts, filters or requests. The
online poker stage, administrative console, and point-form layout stay intact.
"""

from __future__ import annotations


ILLUMINATED_CLASSIC_MARKER = "jj illuminated classic visual theme v2"
ILLUMINATED_DECK_MARKER = 'class="jj-illuminated-deck"'


def transform_index(html: str) -> str:
    """Add a small decorative suit-card illustration without changing controls."""
    if ILLUMINATED_DECK_MARKER in html:
        return html
    anchor = 'id="heroLeaderPoints">0 pt</b></div></article>'
    if html.count(anchor) != 1:
        raise RuntimeError("home hero composition changed; update the art anchor safely")
    deck = (
        'id="heroLeaderPoints">0 pt</b></div>'
        '<div class="jj-illuminated-deck" aria-hidden="true">'
        '<span>♠</span><span>♥</span><span>♦</span><span>♣</span>'
        '</div></article>'
    )
    return html.replace(anchor, deck, 1)

ILLUMINATED_CLASSIC_CSS = r"""

/* jj illuminated classic visual theme v2
   A distinctive editorial, playing-card interface. CSS-only, no asset cost.
   Poker action surfaces and form positioning are deliberately untouched. */
#appView {background:#F5F0E5;}
#appView .main {background:linear-gradient(90deg,rgba(184,147,83,.055) 1px,transparent 1px) 0 0/44px 44px,#F5F0E5;}
#appView .sidebar {background:linear-gradient(160deg,#162C4F 0%,#19233C 65%,#263B51 100%);border-right:3px solid #BE9252;}
#appView .side-brand {border-bottom:1px solid rgba(239,204,139,.32);margin-bottom:17px;padding-bottom:20px;}
#appView .side-brand .brand-mark {background:#F8E4B4;color:#20345A;border:1px solid #FFF4D9;border-radius:8px;transform:rotate(-6deg);box-shadow:4px 4px 0 rgba(255,255,255,.08);font-family:Georgia,serif;}
#appView .side-brand strong {font-family:Georgia,"Times New Roman",serif;font-size:1.17rem;letter-spacing:.035em;}
#appView .side-brand span {color:#E7CA98;}
#appView .sidebar .nav {color:#D5DFED;border-radius:8px;border-left:3px solid transparent;font-weight:760;}
#appView .sidebar .nav:hover {background:rgba(255,255,255,.1);color:#FFFFFF;}
#appView .sidebar .nav.active {color:#232D49;background:linear-gradient(90deg,#FFF0C5,#F6D89B);border-color:#EDB85C;box-shadow:0 5px 16px rgba(8,14,34,.13);}
#appView .sidebar .live-dot {color:#F0D7A8;}
#appView .topbar {background:#FBF6EA;border-bottom:2px solid #D6B477;backdrop-filter:none;}
#appView .topbar .eyebrow {color:#8D6130;}
#appView .topbar h2 {color:#203352;font-family:Georgia,"Yu Mincho","Hiragino Mincho ProN",serif;letter-spacing:.01em;}
#appView .user-chip {border:1px solid #D8C39F;border-radius:8px;background:#FFFDF7;}
#appView .user-chip span {color:#775123;}
#appView .main .section-head {border-bottom:1px solid #CFB27C;padding-bottom:11px;}
#appView .main .section-head h3,
#appView .main .panel>h3 {color:#203352;font-family:Georgia,"Yu Mincho","Hiragino Mincho ProN",serif;letter-spacing:0;}
#appView .main .section-head .eyebrow,
#appView .main .panel>.eyebrow {color:#9A5E2B;}
#appView .main .card:not(.poker-zone):not(.table-side) {border-color:#DCCBB0;box-shadow:0 4px 0 rgba(122,87,52,.035);}

/* Editorial cover: a framed banner and a large suit seal, not a color swap. */
#homeView .hero {border:3px double #E5C68A!important;border-radius:12px;padding:38px;background:linear-gradient(114deg,#223C71 0%,#2C4F91 58%,#62476B 100%)!important;box-shadow:7px 8px 0 #E8D7B4;}
#homeView .hero::before {content:"♠";position:absolute;inset:auto 2% -29% auto;width:auto;height:auto;border:0;border-radius:0;box-shadow:none;color:rgba(252,227,177,.18);font:normal 22rem/1 Georgia,serif;pointer-events:none;}
#homeView .hero::after {content:none;}
#homeView .jj-illuminated-deck {position:absolute;right:34px;top:28px;z-index:0;width:176px;height:145px;display:grid;grid-template-columns:1fr 1fr;align-items:center;justify-items:center;padding:11px;border:5px double #DBB678;border-radius:9px;background:#FFF6DF;box-shadow:7px 8px 0 rgba(9,22,50,.2);transform:rotate(7deg);pointer-events:none;}
#homeView .jj-illuminated-deck span {font:normal 3rem/1 Georgia,serif;color:#263E75;}
#homeView .jj-illuminated-deck span:nth-child(2) {color:#B74762;}
#homeView .jj-illuminated-deck span:nth-child(3) {color:#BA7540;}
#homeView .jj-illuminated-deck span:nth-child(4) {color:#207D71;}
#homeView .hero .eyebrow {display:inline-block;color:#FFE4AA;letter-spacing:.23em;border-bottom:1px solid rgba(255,236,186,.7);padding-bottom:9px;}
#homeView .hero h3 {font-family:Georgia,"Yu Mincho","Hiragino Mincho ProN",serif;font-weight:770;line-height:1.22;letter-spacing:.02em;text-shadow:0 1px 1px rgba(17,29,52,.18);}
#homeView .hero>div:first-child {max-width:65%;}
#homeView .hero p {color:#F2F2FF;line-height:1.8;}
#homeView .hero .primary {color:#233354;background:#FCE6B7;box-shadow:0 4px 0 rgba(0,0,0,.13);border-radius:6px;}
#homeView .hero .soft {color:#FFFFFF;border-color:#F1DAA7;background:rgba(255,255,255,.08);border-radius:6px;}
#homeView .leader-box {border:1px solid rgba(250,224,169,.65);border-radius:8px;background:rgba(16,28,59,.35);backdrop-filter:none;}
#homeView .leader-box span,#homeView .leader-box b {color:#FFE2A1;}
#homeView .kpi {border-radius:10px;background:#F9E4BB;border:2px solid #C69B57!important;box-shadow:6px 7px 0 #E4D1AB!important;}
#homeView .kpi::after {content:"♦";font:normal 9rem/1 Georgia,serif;right:-9px;bottom:-22px;color:rgba(148,86,42,.13);}
#homeView .kpi>strong {color:#253D71;}
#homeView .kpi>span {color:#75451A;}
#homeView .top-grid {gap:14px;}
#homeView .top-player {border-top:4px solid #4D73B7!important;border-radius:9px;background:#FFFDF7;box-shadow:4px 5px 0 rgba(81,91,133,.07)!important;}
#homeView .top-player:nth-child(2) {border-top-color:#5BADA6!important;}
#homeView .top-player:nth-child(3) {border-top-color:#B86D92!important;}
#homeView .top-player:nth-child(4) {border-top-color:#8D79B8!important;}
#homeView .top-player:nth-child(5) {border-top-color:#CC8B55!important;}
#homeView .top-player:first-child {background:#FFF0CE;border-color:#C89C54!important;}
#homeView .top-player:first-child::after {content:"♛";position:absolute;right:12px;top:3px;color:#B58334;font:normal 2.7rem/1 Georgia,serif;opacity:.25;pointer-events:none;}
#homeView .top-player .rank {color:#73572E;letter-spacing:.11em;}
#homeView .top-player b {color:#254C91;}
#homeView .home-columns>.panel {border-radius:10px;position:relative;overflow:hidden;background:#FFFDF7;}
#homeView .home-columns>.panel::before {content:"";display:block;height:5px;margin:-22px -22px 20px;background:#416CB0;}
#homeView .home-columns>.panel:nth-child(2)::before {background:#BC708A;}
#homeView .home-columns>.panel:nth-child(3)::before {background:#3C9285;}
#homeView .weekly-study.card {border-top:4px solid #956BA8;}
#homeView .mobile-quick-point {border:2px solid #C69B57!important;border-radius:10px!important;background:#FFF9EC!important;box-shadow:4px 5px 0 #E6D4B5!important;}
#homeView .mobile-section-title>span {color:#6C4724;background:#F8E0B1;}
#homeView .quick-point-total {background:#233D70;}

/* Three genuinely different podium cards and a legible leaderboard. */
#rankingView .jj-v1243-ranking-head {border-bottom:2px solid #D5B67E;padding-bottom:12px;}
#rankingView .jj-v1243-ranking-grid>article {border:1px solid #D8C29E;border-top:4px solid #5472AD;border-radius:10px;background:#FFFDF8;}
#rankingView .jj-v1243-ranking-grid>article:nth-child(2) {border-top-color:#B77394;}
#rankingView .jj-v1243-ranking-grid>article:nth-child(3) {border-top-color:#3A958C;}
#rankingView .jj-v1243-rank-me>div:first-of-type strong {color:#294D83;}
#rankingView .jj-v1243-rank-row.is-me>span,#rankingView .jj-v1243-rank-row.is-me>b {color:#7B4D27;}
#rankingView .toolbar {border:1px solid #D8C29E;border-radius:10px;background:#FFF9ED;}
#rankingView .segmented button.active {background:#284B85;color:#FFFFFF;box-shadow:none;}
#rankingView .podium-card {position:relative;overflow:hidden;border-radius:10px;border-top:5px solid #B7C3D6!important;background:#FAFCFF;}
#rankingView .podium-card::after {position:absolute;right:10px;top:8px;font:normal 3rem/1 Georgia,serif;opacity:.15;pointer-events:none;}
#rankingView .podium-card:first-child {background:#FFF0CB;border-color:#D4A04F!important;box-shadow:6px 7px 0 rgba(164,124,57,.14);}
#rankingView .podium-card:first-child::after {content:"♛";color:#865014;}
#rankingView .podium-card:nth-child(2) {background:#EDF7F7;border-color:#52A8A0!important;}
#rankingView .podium-card:nth-child(2)::after {content:"♣";color:#287A72;}
#rankingView .podium-card:nth-child(3) {background:#FFF0F4;border-color:#C97A98!important;}
#rankingView .podium-card:nth-child(3)::after {content:"♥";color:#A94267;}
#rankingView .podium-card b {color:#263D70;}
#rankingView .table-card {border-radius:10px;}
#rankingView .table-card th {background:#2A4574;color:#FFF8E6;letter-spacing:.08em;}
#rankingView .table-card tbody tr:nth-child(even) {background:#FBF6EC;}
#rankingView .table-card tbody tr:hover {background:#F1E9D8;}
#rankingView .rank-num {color:#233B69;}

/* Other views share the same architecture, but no poker controls are touched. */
#pointsView .panel,#membersView .panel,#newsView .panel,#labView .panel,#discussionView .panel,#scheduleView .panel {background:#FFFDF7;border-top:4px solid #5273AF;border-radius:10px;}
#pointsView .two-col>.panel:nth-child(2) {border-top-color:#4B9B90;}
#pointsView .chip-entry {background:#FFF8E9;border-color:#D9BF91;}
#pointsView .calc {background:#EAF0FA;border-color:#B7C8DE;}
#pointsView .calc strong {color:#1D477C;}
#pointsView .primary {background:#284D87;color:#FFFFFF;}
#analysisView .jj-analysis-hero,#handAnalysisView .jj-analysis-hero,.jj-analysis-hero {border:3px double #E5C68A;background:linear-gradient(115deg,#223C71,#4C487B);border-radius:10px;box-shadow:5px 6px 0 #E8D7B4;}
.jj-analysis-hero .eyebrow {color:#F7DBA4;}
.jj-analysis-hero p {color:#F0F0FF;}
.jj-analysis-kpi,.jj-analysis-chart-card,.jj-hand-card {border-top:3px solid #6488C0!important;border-radius:9px;}
.jj-analysis-kpi:nth-child(2),.jj-hand-card:nth-child(2n) {border-top-color:#C27695!important;}
.jj-analysis-kpi:nth-child(3) {border-top-color:#52A69E!important;}
.jj-analysis-kpi:nth-child(4) {border-top-color:#C69A50!important;}
.jj-stat,.jj-signal {background:#FFF9ED;border-color:#DFCCAD;}

/* Login has an authentic printed-card look, but same focusable controls. */
#authView.auth-shell {background:linear-gradient(45deg,rgba(196,161,97,.11) 25%,transparent 25%,transparent 75%,rgba(196,161,97,.11) 75%) 0 0/48px 48px,#F5F0E5;}
#authView .auth-card {border:3px double #BA945D;border-radius:10px;background:#FFFDF5;box-shadow:9px 10px 0 #DFCDAE;}
#authView .brand-mark {background:#294B85;border-radius:9px;}
#authView .brand-row h1 span {color:#315AA0;}

@media(max-width:1240px) {
  #homeView .jj-illuminated-deck {width:118px;height:100px;right:20px;top:21px;padding:4px;}
  #homeView .jj-illuminated-deck span {font-size:2rem;}
  #homeView .hero>div:first-child {max-width:75%;}
}

@media(max-width:760px) {
  #appView .main {background:#F5F0E5;}
  #appView .topbar {background:#FFF9EE!important;border-bottom:2px solid #D6B477;backdrop-filter:none!important;}
  #homeView .hero {padding:20px!important;min-height:0;border-width:2px!important;box-shadow:4px 5px 0 #E6D1A9;}
  #homeView .hero>div:first-child {max-width:100%;}
  #homeView .jj-illuminated-deck {display:none;}
  #homeView .hero::before {right:0;bottom:0;font-size:7rem;color:rgba(255,224,167,.13);}
  #homeView .hero::after {content:"♥ ♦ ♣";right:11px;top:12px;font:normal 1rem/1 Georgia,serif;letter-spacing:.3em;color:#F6DAA6;pointer-events:none;opacity:.85;}
  #homeView .hero h3 {font-size:1.8rem!important;line-height:1.24!important;letter-spacing:.01em;}
  #homeView .home-columns>.panel::before {margin:-16px -16px 15px;}
  #homeView .mobile-quick-point {padding:16px!important;}
  #rankingView .toolbar {background:#FFF9ED!important;backdrop-filter:none!important;}
  #rankingView .podium-card {background:#FAFCFF!important;border:1px solid #B7C3D6!important;border-left:5px solid #B7C3D6!important;border-top-width:1px!important;box-shadow:none;}
  #rankingView .podium-card:first-child {background:#FFF0CB!important;border-left-color:#D4A04F!important;}
  #rankingView .podium-card:nth-child(2) {background:#EDF7F7!important;border-left-color:#52A8A0!important;}
  #rankingView .podium-card:nth-child(3) {background:#FFF0F4!important;border-left-color:#C97A98!important;}
  #rankingView .table-card tbody tr {background:#FFFDF7!important;border-left:4px solid #6584B7!important;}
  #rankingView .table-card tbody tr:nth-child(even) {background:#FBF5E9!important;}
  #appView .mobile-dock {background:#1B3157;border:1px solid #C59A5E;backdrop-filter:none;}
  #appView .mobile-dock button.active {background:#FCE4B2;color:#213456;}
  #appView .mobile-dock .mobile-point-nav {background:#F4CF7D!important;color:#213456!important;box-shadow:0 3px 0 #B88943;}
}
@media(max-width:420px) {
  #homeView .hero::after {display:none;}
  #homeView .hero::before {font-size:5rem;}
  #rankingView .podium-card::after {font-size:2rem;}
}
"""


def transform_styles(css: str) -> str:
    """Append exactly once after every historical browser styling transform."""
    if ILLUMINATED_CLASSIC_MARKER in css:
        return css
    return css.rstrip() + ILLUMINATED_CLASSIC_CSS + "\n"


__all__ = ["ILLUMINATED_CLASSIC_MARKER", "ILLUMINATED_CLASSIC_CSS", "ILLUMINATED_DECK_MARKER", "transform_index", "transform_styles"]
