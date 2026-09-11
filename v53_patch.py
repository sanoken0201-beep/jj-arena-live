from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.24.1"', 'version="1.24.2"')
    text = text.replace('"version":"1.24.1"', '"version":"1.24.2"')
    text = text.replace('request.url.query == "v=53"', 'request.url.query == "v=54"')
    path.write_text(text, encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.2 learning-card contrast hardening"
    if marker in text:
        return

    addon = r'''

/* v1.24.2 learning-card contrast hardening
   Learning cards live on a dark green surface. Do not inherit page/link colors:
   every text role gets an explicit high-contrast color so Safari, :visited,
   theme changes, and future home-page styles cannot make the copy unreadable. */
.jj-learning-share .jj-study-card,
.jj-learning-share .jj-video-card{
  color:#f4f8f6!important;
  background:rgba(255,255,255,.035)!important;
  border-color:rgba(219,235,226,.14)!important;
}
.jj-learning-share .jj-study-card:visited,
.jj-learning-share .jj-video-card:visited{color:#f4f8f6!important}
.jj-learning-share .jj-study-card:hover,
.jj-learning-share .jj-video-card:hover,
.jj-learning-share .jj-study-card:focus-visible,
.jj-learning-share .jj-video-card:focus-visible{
  color:#fff!important;
  border-color:rgba(242,205,99,.5)!important;
  background:rgba(255,255,255,.055)!important;
}
.jj-learning-share .jj-study-card h3,
.jj-learning-share .jj-video-card h3{
  color:#f7fbf9!important;
  opacity:1!important;
  text-shadow:0 1px 2px rgba(0,0,0,.28);
}
.jj-learning-share .jj-study-card p,
.jj-learning-share .jj-video-card p{
  color:#c9d6d0!important;
  opacity:1!important;
}
.jj-learning-share .jj-study-meta{
  color:#b8c8c0!important;
  opacity:1!important;
}
.jj-learning-share .jj-study-meta>span:not(.jj-study-source):not(.jj-video-kind){
  color:#b8c8c0!important;
  opacity:1!important;
}
.jj-learning-share .jj-study-source{
  color:#9ee2c2!important;
  background:rgba(78,183,137,.16)!important;
  opacity:1!important;
}
.jj-learning-share .jj-video-kind{
  color:#9ee2c2!important;
  opacity:1!important;
}
.jj-learning-share .jj-video-kind.is-motivation{color:#f1d47c!important}
.jj-learning-share .jj-study-card footer,
.jj-learning-share .jj-video-card footer{
  color:#aebeb6!important;
  opacity:1!important;
}
.jj-learning-share .jj-study-card footer>span,
.jj-learning-share .jj-video-card footer>span{
  color:#aebeb6!important;
  opacity:1!important;
}
.jj-learning-share .jj-study-card footer b,
.jj-learning-share .jj-video-card footer b{
  color:#f3d981!important;
  opacity:1!important;
}
@media(max-width:760px){
  .jj-learning-share .jj-study-card h3,
  .jj-learning-share .jj-video-card h3{
    font-size:.9rem!important;
    line-height:1.5!important;
  }
  .jj-learning-share .jj-study-meta{font-size:.66rem!important}
  .jj-learning-share .jj-study-card footer,
  .jj-learning-share .jj-video-card footer{font-size:.68rem!important}
}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=53", "?v=54")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v53(?:-[A-Za-z0-9_-]+)?", "jj-arena-live-v54", text)
    path.write_text(text, encoding="utf-8")
