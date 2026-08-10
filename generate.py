#!/usr/bin/env python3
"""Static-site generator for the Neuro Anesthesia Protocols site.

Usage:
    python3 generate.py [input_file]

If no input file is given, ./protocols.txt is used.

For each protocol listed in the input file the script writes
protocols/<slug>.html.  If a matching HTML fragment exists at
content/<slug>.html its contents are embedded in the page body; otherwise a
placeholder is shown.  It also rebuilds index.html and the shared header/nav.

Re-run this script any time the input file changes or a Word document has been
converted to an HTML fragment and dropped into content/.
"""

from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SITE_TITLE = "Neuro Anesthesia Protocols"
SITE_SUBTITLE = "HBMD.org"
SITE_TAGLINE = (
    "A concise, up-to-date reference of neuroanesthesiology protocols."
)
HEADER_IMAGE = "assets/neurons.svg"   # two neurons connecting (swap when supplied)
FOOTER_DISCLAIMER = (
    "For clinical reference by qualified anesthesia providers. Protocols are "
    "guidance, not a substitute for individual clinical judgement."
)

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
PROTOCOLS_DIR = ROOT / "protocols"


# --------------------------------------------------------------------------- #
# Input parsing
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def parse_input(path: Path):
    """Return a list of sections: [{"name": str, "items": [{title, slug}]}]."""
    sections: list[dict] = []
    current = {"name": "", "items": []}
    seen_slugs: set[str] = set()

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"^==\s*(.+?)\s*==$", line)
        if m:
            if current["items"] or current["name"]:
                sections.append(current)
            current = {"name": m.group(1), "items": []}
            continue

        if "|" in line:
            title, slug = (p.strip() for p in line.split("|", 1))
            slug = slugify(slug)
        else:
            title, slug = line, slugify(line)

        # guarantee uniqueness
        base, n = slug, 2
        while slug in seen_slugs:
            slug = f"{base}-{n}"
            n += 1
        seen_slugs.add(slug)

        current["items"].append({"title": title, "slug": slug})

    if current["items"] or current["name"]:
        sections.append(current)
    return sections


# --------------------------------------------------------------------------- #
# HTML fragments
# --------------------------------------------------------------------------- #
def nav_html(sections, prefix: str, active_slug: str | None) -> str:
    """Build the shared navigation. `prefix` is "" at root, "../" one level deep."""
    items = [f'<li><a href="{prefix}index.html">Home</a></li>']
    for sec in sections:
        name = html.escape(sec["name"] or "Protocols")
        links = []
        for it in sec["items"]:
            cls = ' class="is-active"' if it["slug"] == active_slug else ""
            href = f'{prefix}protocols/{it["slug"]}.html'
            links.append(f'<li><a{cls} href="{href}">{html.escape(it["title"])}</a></li>')
        items.append(
            '<li class="dropdown">'
            f'<button type="button" aria-haspopup="true" aria-expanded="false">{name}</button>'
            f'<ul class="dropdown__menu">{"".join(links)}</ul>'
            "</li>"
        )
    return (
        '<nav class="main-nav" id="main-nav" aria-label="Protocols">'
        f'<ul>{"".join(items)}</ul></nav>'
    )


def header_html(sections, prefix: str, active_slug: str | None) -> str:
    return f"""<header class="site-header">
  <div class="container header-inner">
    <a class="brand" href="{prefix}index.html">
      <img class="brand__logo" src="{prefix}{HEADER_IMAGE}" alt="Two neurons connecting" />
      <span class="brand__text">
        <span class="brand__title">{html.escape(SITE_TITLE)}</span>
        <span class="brand__sub">{html.escape(SITE_SUBTITLE)}</span>
      </span>
    </a>
    <button class="nav-toggle" id="nav-toggle" aria-controls="main-nav" aria-expanded="false">
      <span aria-hidden="true">&#9776;</span><span class="sr-only"> Menu</span>
    </button>
    {nav_html(sections, prefix, active_slug)}
  </div>
</header>"""


def footer_html() -> str:
    year = date.today().year
    return f"""<footer class="site-footer">
  <div class="container footer-inner">
    <span class="disclaimer">{html.escape(FOOTER_DISCLAIMER)}</span>
    <span>&copy; {year} HBMD.org</span>
  </div>
</footer>"""


NAV_JS = """<script>
(function () {
  var toggle = document.getElementById('nav-toggle');
  var nav = document.getElementById('main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  // Mobile: tap a dropdown label to expand it.
  document.querySelectorAll('.dropdown > button').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      if (window.matchMedia('(max-width: 820px)').matches) {
        e.preventDefault();
        btn.parentElement.classList.toggle('open');
      }
    });
  });
})();
</script>"""


def page(title: str, prefix: str, body: str, sections, active_slug=None) -> str:
    full_title = f"{title} — {SITE_TITLE}" if title != SITE_TITLE else SITE_TITLE
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(full_title)}</title>
  <link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml" />
  <link rel="stylesheet" href="{prefix}assets/style.css" />
</head>
<body>
{header_html(sections, prefix, active_slug)}
{body}
{footer_html()}
{NAV_JS}
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Page builders
# --------------------------------------------------------------------------- #
def build_index(sections) -> str:
    cards = []
    for sec in sections:
        cards.append(f'<h2 class="section-title">{html.escape(sec["name"] or "Protocols")}</h2>')
        cards.append('<div class="card-grid">')
        for it in sec["items"]:
            ready = (CONTENT_DIR / f'{it["slug"]}.html').exists()
            meta = ('<span class="card__meta">Open protocol <span class="arrow">&rarr;</span></span>'
                    if ready else
                    '<span class="card__meta"><span class="badge">Draft</span></span>')
            cards.append(
                f'<a class="card" href="protocols/{it["slug"]}.html">'
                f'<span class="card__eyebrow">{html.escape(sec["name"] or "Protocol")}</span>'
                f'<span class="card__title">{html.escape(it["title"])}</span>'
                f"{meta}</a>"
            )
        cards.append("</div>")

    hero = f"""<section class="hero">
  <div class="container hero-inner">
    <div>
      <h1>{html.escape(SITE_TITLE)}</h1>
      <p>{html.escape(SITE_TAGLINE)}</p>
    </div>
    <img class="hero__art" src="{HEADER_IMAGE}" alt="Two neurons connecting" />
  </div>
</section>"""

    body = f'{hero}\n<main><div class="container">{"".join(cards)}</div></main>'
    return page(SITE_TITLE, "", body, sections)


PLACEHOLDER_ICON = (
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" '
    'stroke="#0d9488" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 9v4"/><path d="M12 17h.01"/>'
    '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
    "</svg>"
)


def build_protocol(sec_name: str, item: dict, sections) -> str:
    slug, title = item["slug"], item["title"]
    fragment = CONTENT_DIR / f"{slug}.html"

    if fragment.exists():
        inner = fragment.read_text(encoding="utf-8")
    else:
        inner = f"""<div class="placeholder-note">
  {PLACEHOLDER_ICON}
  <div>
    <strong>Placeholder page.</strong> The full protocol has not been published yet.
    To publish it, convert the Word document to an HTML fragment and save it as
    <code>content/{slug}.html</code>, then re-run <code>generate.py</code>.
  </div>
</div>
<h2>Overview</h2>
<p>Content for the <strong>{html.escape(title)}</strong> protocol will appear here.</p>
<h2>Sections to include</h2>
<ul>
  <li>Preoperative assessment &amp; optimization</li>
  <li>Monitoring &amp; access</li>
  <li>Induction &amp; airway</li>
  <li>Maintenance &amp; neuromonitoring considerations</li>
  <li>Hemodynamic &amp; ICP goals</li>
  <li>Emergence &amp; postoperative disposition</li>
</ul>"""

    body = f"""<section class="subhero">
  <div class="container subhero-inner">
    <p class="eyebrow">{html.escape(sec_name or "Protocol")}</p>
    <h1>{html.escape(title)}</h1>
  </div>
</section>
<main><div class="container article-wrap">
  <div>
    <a class="backlink" href="../index.html">All protocols</a>
    <article class="prose">{inner}</article>
  </div>
</div></main>"""
    return page(title, "../", body, sections, active_slug=slug)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "protocols.txt"
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    sections = parse_input(input_path)
    CONTENT_DIR.mkdir(exist_ok=True)
    PROTOCOLS_DIR.mkdir(exist_ok=True)

    # Clean out previously generated protocol pages so removed items disappear.
    for old in PROTOCOLS_DIR.glob("*.html"):
        old.unlink()

    (ROOT / "index.html").write_text(build_index(sections), encoding="utf-8")

    count = 0
    for sec in sections:
        for item in sec["items"]:
            out = PROTOCOLS_DIR / f'{item["slug"]}.html'
            out.write_text(build_protocol(sec["name"], item, sections), encoding="utf-8")
            count += 1

    print(f"Generated index.html and {count} protocol page(s) from {input_path.name}.")


if __name__ == "__main__":
    main()
