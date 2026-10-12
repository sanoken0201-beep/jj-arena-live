"""Build-time, inline SVG Jack-knight brand art for the JJ Arena home screen.

No generated bitmap, third-party image, costume suit-pattern, marketing slogan,
network request, layout reordering or JavaScript. The primary asset is a small
engraving-like half-length knight: card-court silhouette, kettle/bascinet-like
helmet, mantle and sword, simplified for 70px mobile presentation.
"""

MARKER = "jj jack knight screen art 2026-10-12"

# Deliberately drawn as vector geometry, not as a free-standing generated image.
# No pips on the armor and no arbitrary catchphrase.
KNIGHT_SVG = """<svg class="jj-jack-knight" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 260" aria-hidden="true" focusable="false">
  <path d="M27 21h156v213H27z" fill="#15244B" stroke="#E5B960" stroke-width="3"/>
  <path d="M33 27h144v201H33z" fill="#263C7F" stroke="#8BDDF2" stroke-width="1.5"/>
  <path d="M33 173 177 42v64L61 228H33Z" fill="#CB4295" opacity=".82"/>
  <path d="m33 107 80-80h40L33 147z" fill="#27C7D9" opacity=".45"/>
  <path d="M50 222q2-55 30-78l24 11 27-12q34 22 33 79" fill="#C14B71" stroke="#0C1837" stroke-width="4"/>
  <path d="M67 168q-22 10-21 54h38l15-58ZM144 164q20 14 23 58h-41l-14-59Z" fill="#AFC9DC" stroke="#111D42" stroke-width="4"/>
  <path d="M61 191q12-19 25-20l15 29-7 25H57q-3-18 4-34ZM150 188q-11-15-25-18l-17 29 8 26h38q3-20-4-37Z" fill="#EDF0E3" stroke="#1B2850" stroke-width="3"/>
  <path d="M76 160 89 148h35l12 12-14 61H90z" fill="#4C668B" stroke="#111E3F" stroke-width="4"/>
  <path d="m90 159 17 18 16-18-6 63H96z" fill="#DADFD6"/>
  <path d="m107 174 0 45" fill="none" stroke="#DBA64B" stroke-width="3"/>
  <path d="M91 148v-21l31 1v19l-14 17z" fill="#C18E72" stroke="#182340" stroke-width="3"/>
  <path d="M80 98q-1-32 28-33 30 0 27 34l-5 27-17 16-20-6-12-17z" fill="#E6B48D" stroke="#122041" stroke-width="4"/>
  <path d="m81 110 16 7 18 1 17-10-2 17-17 16-20-6z" fill="#B27D63" opacity=".7"/>
  <path d="m91 105 9-3m18 2 9-4" fill="none" stroke="#17223C" stroke-width="3" stroke-linecap="round"/>
  <path d="m108 108-3 12 10 2" fill="none" stroke="#9B634E" stroke-width="2.5" stroke-linecap="round"/>
  <path d="m103 129 11 2 7-4" fill="none" stroke="#703D3F" stroke-width="2.7" stroke-linecap="round"/>
  <path d="M75 96q-9-50 29-61 41-7 45 46l-12 17-5-16-45 1-2 16z" fill="#B8CDD2" stroke="#18284D" stroke-width="4"/>
  <path d="M88 74q6-28 27-28 16 0 21 28" fill="#F4E8BD" stroke="#253B60" stroke-width="3"/>
  <path d="m67 84 14-12 60-2 16 13-8 10-68-1z" fill="#738EA4" stroke="#132244" stroke-width="3"/>
  <path d="M101 40Q118 8 150 17q-21 8-29 29z" fill="#F3BC4B" stroke="#17233C" stroke-width="3"/>
  <path d="M111 39q25-22 53-17-19 23-38 28z" fill="#F05898" stroke="#162644" stroke-width="3"/>
  <path d="M77 165q-18-8-28 6l9 16 26-5ZM141 164q17-7 24 7l-10 19-25-8z" fill="#E4BD71" stroke="#162546" stroke-width="3"/>
  <path d="M56 215h103" stroke="#D7B55A" stroke-width="4"/>
  <path d="M153 111v104m-11-96 23 0m-12-26v15" stroke="#FAE5B1" stroke-width="6" stroke-linecap="round"/>
  <path d="M153 216 146 227h14z" fill="#FBE7BF" stroke="#18264F" stroke-width="2"/>
  <path d="m150 116 3-12 3 12" fill="none" stroke="#172346" stroke-width="3"/>
  <path d="M39 38v14h7M172 38v14h-7M39 215v-14h7M172 215v-14h-7" fill="none" stroke="#F4CC73" stroke-width="2"/>
  <text x="43" y="62" font-family="Georgia,serif" font-size="24" font-weight="700" fill="#FBE7BD">J</text>
</svg>"""

CSS = r"""
/* JJ Jack-knight: original, decorative screen illustration. Gameplay excluded. */
/* No view fade on this brand-heavy panel: preserve full text contrast on entry. */
#homeView.active-view{animation:none!important;opacity:1}
#homeView .hero.jj-jack-hero{
  background:#1B2855!important;
  border:1px solid #657CC5;
  box-shadow:0 14px 34px rgba(17,30,73,.15);
}
#homeView .hero.jj-jack-hero:before{
  content:"";position:absolute;right:-5%;bottom:-45%;width:48%;height:120%;
  background:#452F82;transform:skewX(-16deg);border:0;border-radius:0;box-shadow:none;
  pointer-events:none;
}
#homeView .jj-jack-hero .eyebrow{color:#9AE7EF}
#homeView .jj-jack-hero p{color:#E4E9FA!important}
#homeView .jj-jack-hero .leader-box{background:rgba(21,32,74,.94)!important;backdrop-filter:none}
#homeView .jj-jack-hero .primary{background:#F5C557;color:#1B2855}
#homeView .jj-jack-hero .soft{background:#33477D;color:#fff;border-color:#7385BD}
#homeView .jj-jack-knight{
  position:absolute;right:245px;bottom:-60px;width:190px;height:235px;
  display:block;flex:none;pointer-events:none;user-select:none;
  opacity:1;z-index:0;filter:none;
}
#homeView .jj-jack-hero>div{position:relative;z-index:1}
@media(max-width:1200px){
  #homeView .jj-jack-knight{right:248px;width:146px;height:181px;bottom:-25px;opacity:.92}
}
@media(max-width:760px){
  #homeView .jj-jack-knight{right:10px;top:8px;bottom:auto;width:124px;height:153px;opacity:1}
  #homeView .jj-jack-hero .eyebrow{max-width:calc(100% - 136px)}
  #homeView .jj-jack-hero h3{max-width:calc(100% - 112px)}
}
@media(max-width:560px){
  #homeView .jj-jack-hero p{max-width:calc(100% - 136px)!important}
}
@media(max-width:360px){
  #homeView .jj-jack-knight{right:9px;top:8px;width:105px;height:130px}
}
"""

HERO = '<article class="hero card">'
KNIGHT_INSERTION = '<div class="leader-box">'


def transform_index(html: str) -> str:
    if MARKER in html:
        return html
    if html.count(HERO) != 1 or html.count(KNIGHT_INSERTION) != 1:
        raise RuntimeError("Jack knight home hero drift")
    html = html.replace(HERO, '<article class="hero card jj-jack-hero">', 1)
    html = html.replace(KNIGHT_INSERTION, KNIGHT_SVG + KNIGHT_INSERTION, 1)
    # No invented catchphrase. Keep factual home paragraph and all buttons.
    home_heading = "<h3>次の1ハンドを、<br>みんなで。</h3>"
    if html.count(home_heading) != 1:
        raise RuntimeError("Jack knight original home heading drift")
    html = html.replace(home_heading, "<h3>JJ Arena</h3>", 1)
    # Short factual navigation, no promotional or invented catchphrase.
    previous_intro = "後期ランキング、活動予定、学習、戦略議論、リアルタイムNLHをひとつに。JJの運営とプレイを、より速くシンプルに。"
    if html.count(previous_intro) != 1:
        raise RuntimeError("Jack knight home description drift")
    html = html.replace(previous_intro, "予定・ランキング<br>学習・オンライン卓", 1)
    return html + "\n<!-- " + MARKER + " -->\n"


def transform_styles(css: str) -> str:
    if MARKER in css:
        return css
    if ".hero:before" not in css:
        raise RuntimeError("Jack knight hero CSS drift")
    return css + CSS + "\n/* " + MARKER + " */\n"


__all__ = ["MARKER", "KNIGHT_SVG", "CSS", "transform_index", "transform_styles"]
