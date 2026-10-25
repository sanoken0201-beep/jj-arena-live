"""Small, strictly scoped visual theme for JJ Arena's non-gameplay views.

Only the final compiled CSS is extended. Canonical materialized assets, point
forms, online poker controls, admin pages and JavaScript remain untouched.
"""

from __future__ import annotations


ILLUMINATED_CLASSIC_MARKER = "jj illuminated classic visual theme v1"

ILLUMINATED_CLASSIC_CSS = r"""

/* jj illuminated classic visual theme v1
   Color and low-cost decorative changes only. Do not change form geometry,
   gameplay styles, browser scripts, navigation or ranking layout/order. */
#homeView .hero {
  background:radial-gradient(circle at 86% 10%,rgba(255,229,167,.10),transparent 25%),
             linear-gradient(135deg,#244A9E 0%,#315FC5 100%);
  box-shadow:0 24px 54px rgba(40,73,143,.15);
}
#homeView .hero::before {
  content:"♠";
  right:3%;bottom:-17%;width:auto;height:auto;border:0;border-radius:0;box-shadow:none;
  color:rgba(255,249,238,.17);font:normal 19rem/1 Georgia,"Times New Roman",serif;
  pointer-events:none;
}
#homeView .hero::after {
  content:"♥";position:absolute;right:7%;top:3%;
  color:rgba(255,218,230,.26);font:normal 4.2rem/1 Georgia,"Times New Roman",serif;
  pointer-events:none;
}
#homeView .hero .eyebrow {color:#FFF0C7;}
#homeView .hero p {color:#EDF2FF;}
#homeView .hero .primary {background:#FFF9EE;color:#28365C;box-shadow:none;}
#homeView .hero .soft {background:rgba(255,255,255,.13);color:#FFFFFF;border-color:rgba(255,255,255,.38);}
#homeView .leader-box b {color:#FFE1A0;}
#homeView .kpi {background:linear-gradient(180deg,#FFFDF8,#FFF1DB);}
#homeView .kpi::after {content:"♦";color:rgba(215,170,72,.17);}
#homeView .kpi>strong {color:#315FC5;}
#homeView .kpi>span {color:#846012;}
#homeView .top-player:first-child {
  background:linear-gradient(145deg,#FFFDF8,#FFF3D5);border-color:#E5D19B;
}
#homeView .top-player:first-child::after {
  content:"♣";position:absolute;right:9px;top:4px;
  color:rgba(14,117,109,.15);font:normal 3rem/1 Georgia,"Times New Roman",serif;
  pointer-events:none;
}
#homeView .top-player b {color:#315FC5;}
#homeView .section-head .eyebrow,
#homeView .home-columns .eyebrow,
#homeView .section-head .link-btn {color:#315FC5;}

#rankingView .toolbar {background:#FFFDFA;border-color:#E9E1D3;}
#rankingView .segmented button.active {background:#EEF3FF;color:#315FC5;}
#rankingView .podium-card {background:#FFFFFF;border-color:#E9E1D3;}
#rankingView .podium-card:first-child {
  background:linear-gradient(180deg,#FFFDF5,#FFF1CB);border-color:#D7AA48;
  box-shadow:0 14px 35px rgba(132,96,18,.08);
}
#rankingView .podium-card:nth-child(2) {border-color:#83C9BA;background:#F5FFFC;}
#rankingView .podium-card:nth-child(3) {border-color:#EAB1C6;background:#FFF8FB;}
#rankingView .podium-card b {color:#28365C;}
#rankingView .table-card th {background:#FFF9EE;color:#28365C;}
#rankingView .rank-num {color:#28365C;}

/* Point entry: decorate only surrounding surfaces, never the form or inputs. */
#pointsView .panel {background:#FFFDFA;border-color:#E9E1D3;}
#pointsView .panel>.eyebrow {color:#315FC5;}
#pointsView .panel>h3 {color:#28365C;}

/* Auth card: preserve its JJ watermark and every login control. */
#authView.auth-shell {
  background:radial-gradient(circle at 12% 16%,rgba(215,170,72,.12),transparent 28%),
             radial-gradient(circle at 86% 82%,rgba(49,95,197,.13),transparent 32%),
             linear-gradient(145deg,#FFF9EE,#F0F4FC);
}
#authView .auth-card {background:#FFFDFA;border-color:#E9E1D3;}
#authView .brand-mark {background:linear-gradient(145deg,#315FC5,#244A9E);}
#authView .brand-row h1 span {color:#315FC5;}

@media (max-width:760px) {
  #homeView .hero::before {right:-8px;bottom:4%;font-size:6rem;color:rgba(255,249,238,.13);}
  #homeView .hero::after {display:none;}
}
@media (max-width:420px) {
  #homeView .hero::before {display:none;}
}
"""


def transform_styles(css: str) -> str:
    """Append exactly once after every historical browser styling transform."""
    if ILLUMINATED_CLASSIC_MARKER in css:
        return css
    return css.rstrip() + ILLUMINATED_CLASSIC_CSS + "\n"


__all__ = ["ILLUMINATED_CLASSIC_MARKER", "ILLUMINATED_CLASSIC_CSS", "transform_styles"]
