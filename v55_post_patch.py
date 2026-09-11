from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    """Final v1.24.4 accessibility/touch-target hardening.

    The earlier stacked branch temporarily used this layer to roll release IDs
    back while another Work stream was active. v1.24.4 is now the authoritative
    release, so this final layer only strengthens interaction targets and never
    changes version/cache identifiers.
    """
    styles = root / "static" / "styles.css"
    text = styles.read_text(encoding="utf-8")
    marker = "v1.24.4 final analysis touch targets"
    if marker in text:
        return
    addon = r'''

/* v1.24.4 final analysis touch targets */
.jj-v1244-focus-card>button,
.jj-v1244-focus-hand-grid>button,
.jj-v1244-focus-hands-head .text-btn{
  min-height:44px;
}
'''
    styles.write_text(text.rstrip() + addon + "\n", encoding="utf-8")
