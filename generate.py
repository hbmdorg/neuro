#!/usr/bin/env python3
"""Static-site generator for the Neuro Anesthesia Protocols site.

Usage:
    python3 generate.py [input_file]

If no input file is given, ./protocols.txt is used.

For each protocol listed in the input file the script writes
protocols/<slug>.html.  The page body comes from, in order of preference:

    1. content/<slug>.md    — Markdown, rendered in the browser at view time
       (marked.js + DOMPurify).  Edit the markdown and redeploy it alone; the
       page updates with no site rebuild.  When a .md exists nothing else is
       considered.
    2. content/<slug>.html  — a hand-authored HTML fragment, or
    3. content/<slug>.rtf   — an RTF document (e.g. saved from Word); its
       structure is preserved and converted to HTML while its own fonts and
       colours are stripped so the site's stylesheet governs the look, or
    4. a generated placeholder when none exists.

It also rebuilds index.html and the shared header/nav.

RTF conversion uses `textutil` (macOS) or `soffice`/`libreoffice` when present,
falling back to a built-in lightweight parser otherwise.

Re-run this script any time the input file changes or a source document has
been dropped into content/.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SITE_TITLE = "Neuroanesthesiology Protocols"
SITE_SUBTITLE = "HBMD.org"
SITE_TAGLINE = (
    "A concise, up-to-date reference of neuroanesthesiology protocols."
)
HEADER_IMAGE = "assets/neurons.svg"   # hero artwork: two neurons connecting (swap when supplied)
LOGO_IMAGE = "assets/gaba-receptor.svg"   # brand mark + favicon (GABA-A receptor)
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
# RTF -> structured HTML fragment
# --------------------------------------------------------------------------- #
# Tags we keep from a converted document. Everything else (spans, fonts, divs,
# style/class attributes) is unwrapped so the site stylesheet controls the look.
_KEEP_TAGS = {
    "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "sub", "sup",
    "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "a", "code", "pre",
}
_KEEP_ATTRS = {
    "a": {"href"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
_VOID_TAGS = {"br", "hr"}


class _Sanitizer(HTMLParser):
    """Reduce arbitrary HTML to a clean, semantic, unstyled fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _KEEP_TAGS:
            keep = _KEEP_ATTRS.get(tag, set())
            kept = "".join(
                f' {k}="{html.escape(v or "", quote=True)}"'
                for k, v in attrs if k in keep
            )
            self.out.append(f"<{tag}{kept}>")

    def handle_startendtag(self, tag, attrs):
        if tag in _VOID_TAGS:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in _KEEP_TAGS and tag not in _VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self.out)


def _clean_html_fragment(raw: str) -> str:
    """Keep only the <body>, strip styling, and tidy up whitespace."""
    m = re.search(r"<body[^>]*>(.*)</body>", raw, re.I | re.S)
    body = m.group(1) if m else raw
    body = re.sub(r"<(script|style)\b.*?</\1>", "", body, flags=re.I | re.S)

    parser = _Sanitizer()
    parser.feed(body)
    frag = parser.result()

    # Promote short, fully-bold paragraphs to headings so the site's heading
    # styles apply to what were visually headings in the document.
    def _promote(match: re.Match) -> str:
        text = match.group(1).strip()
        plain = re.sub(r"<[^>]+>", "", text).strip()
        if plain and len(plain) <= 80 and not plain.endswith((".", ":", ";", ",")):
            return f"<h2>{plain}</h2>"
        return match.group(0)

    frag = re.sub(
        r"<p>\s*<(?:strong|b)>(.*?)</(?:strong|b)>\s*</p>",
        _promote, frag, flags=re.I | re.S,
    )

    # Collapse the insignificant whitespace/newlines the converter inserts when
    # it wraps long lines, then put block-level tags on their own lines so the
    # generated source is tidy. Inline tags (b, i, u, a, br) stay inline.
    frag = re.sub(r"[ \t\r\n]+", " ", frag)
    frag = re.sub(
        r"\s*<(/?(?:p|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|pre))"
        r"(\b[^>]*)?>\s*",
        lambda m: f"\n<{m.group(1)}{m.group(2) or ''}>",
        frag,
    )
    # drop empty / whitespace-only / <br>-only spacer paragraphs
    frag = re.sub(r"<p>\s*(?:<br\s*/?>|&nbsp;|\s)*</p>", "", frag)
    frag = re.sub(r"\n{2,}", "\n", frag)
    return frag.strip()


def _convert_with_textutil(rtf: Path) -> str | None:
    exe = shutil.which("textutil")           # macOS
    if not exe:
        return None
    res = subprocess.run(
        [exe, "-convert", "html", "-stdout", str(rtf)],
        capture_output=True,
    )
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", errors="replace")


def _convert_with_soffice(rtf: Path) -> str | None:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as prof:
        res = subprocess.run(
            [exe, "--headless", f"-env:UserInstallation=file://{prof}",
             "--convert-to", "html:HTML", "--outdir", tmp, str(rtf)],
            capture_output=True,
        )
        if res.returncode != 0:
            return None
        produced = list(Path(tmp).glob("*.htm*"))
        if not produced:
            return None
        return produced[0].read_text(encoding="utf-8", errors="replace")


def _convert_with_builtin(rtf: Path) -> str:
    """Minimal pure-Python RTF reader: paragraphs, bold/italic/underline,
    bullets and unicode escapes. Lower fidelity than textutil/soffice."""
    data = rtf.read_text(encoding="latin-1", errors="replace")

    # Drop binary/def groups we never render.
    data = re.sub(r"\\\*?\\(?:fonttbl|colortbl|stylesheet|info|pict|"
                  r"themedata|colorschememapping)[^{}]*", "", data)

    out: list[str] = []
    i, n = 0, len(data)
    para: list[str] = []
    states = [{"b": False, "i": False, "u": False}]

    def flush_para():
        text = "".join(para).strip()
        para.clear()
        if text:
            out.append(f"<p>{text}</p>")

    def esc(ch: str) -> str:
        return html.escape(ch, quote=False)

    while i < n:
        c = data[i]
        if c == "{":
            states.append(dict(states[-1]))
            i += 1
        elif c == "}":
            if len(states) > 1:
                states.pop()
            i += 1
        elif c == "\\":
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?", data[i:])
            if m:
                word, arg = m.group(1), m.group(2)
                i += m.end()
                if word == "par" or word == "pard":
                    if word == "par":
                        flush_para()
                elif word in ("line",):
                    para.append("<br>")
                elif word == "tab":
                    para.append(" &nbsp; ")
                elif word == "b":
                    on = arg != "0"
                    states[-1]["b"] = on
                    para.append("<strong>" if on else "</strong>")
                elif word == "i":
                    on = arg != "0"
                    states[-1]["i"] = on
                    para.append("<em>" if on else "</em>")
                elif word in ("ul", "ulnone"):
                    on = word == "ul" and arg != "0"
                    states[-1]["u"] = on
                    para.append("<u>" if on else "</u>")
                elif word == "bullet":
                    para.append("&bull; ")
                elif word == "u":            # \uNNNN unicode
                    try:
                        para.append(esc(chr(int(arg))))
                    except (TypeError, ValueError):
                        pass
                # all other control words ignored
            else:
                # escaped literal char: \{ \} \\ and \<punctuation> (e.g. \&)
                if i + 1 < n and not data[i + 1].isalnum():
                    para.append(esc(data[i + 1]))
                    i += 2
                else:
                    i += 1
        else:
            if c not in "\r\n":
                para.append(esc(c))
            i += 1

    flush_para()
    return "\n".join(out)


def rtf_to_fragment(rtf: Path) -> str:
    raw = _convert_with_textutil(rtf) or _convert_with_soffice(rtf)
    if raw is not None:
        return _clean_html_fragment(raw)
    return _clean_html_fragment(_convert_with_builtin(rtf))


# Source precedence for a protocol's content, highest first:
#   .md   -> rendered in the browser from the raw file (edit & redeploy the
#            markdown alone, no site rebuild needed)
#   .html -> hand-authored fragment embedded at build time
#   .rtf  -> converted to HTML at build time
_SOURCE_ORDER = ("md", "html", "rtf")


def source_for(slug: str):
    """Return (ext, path) for the highest-precedence source, or (None, None)."""
    for ext in _SOURCE_ORDER:
        p = CONTENT_DIR / f"{slug}.{ext}"
        if p.exists():
            return ext, p
    return None, None


def has_source(slug: str) -> bool:
    return source_for(slug)[0] is not None


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
      <img class="brand__logo" src="{prefix}{LOGO_IMAGE}" alt="GABA receptor logo" />
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
  <link rel="icon" href="{prefix}{LOGO_IMAGE}" type="image/svg+xml" />
  <link rel="stylesheet" href="{prefix}assets/style.css" />
  <script data-goatcounter="https://hbmd.goatcounter.com/count"
      async src="//gc.zgo.at/count.js"></script>
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
            ready = has_source(it["slug"])
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


# Client-side Markdown rendering. Loaded only on pages whose source is a .md
# file: the raw markdown is fetched at view time, parsed with marked.js and
# sanitised with DOMPurify, then injected into the .prose article. Editing the
# markdown and redeploying updates the page without rebuilding the site.
def md_render_scripts(slug: str) -> str:
    return """<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.1.6/purify.min.js"></script>
<script>
(function () {
  var el = document.getElementById('md-content');
  if (!el) return;
  fetch(el.getAttribute('data-src'), { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
    .then(function (md) {
      if (window.marked && marked.setOptions) marked.setOptions({ gfm: true });
      var raw = window.marked ? (marked.parse ? marked.parse(md) : marked(md)) : md;
      el.innerHTML = window.DOMPurify ? DOMPurify.sanitize(raw) : raw;
      el.classList.remove('md-loading');
      buildToc(el);
    })
    .catch(function (e) {
      el.classList.remove('md-loading');
      el.innerHTML = '<div class="placeholder-note"><div><strong>Could not load content.</strong> ' +
        '(' + e.message + ') If you opened this file directly from disk, browsers block loading the ' +
        'markdown \\u2014 use a local web server (<code>python3 -m http.server</code>) or the published site.</div></div>';
    });

  // Build a linked table of contents from the rendered h2/h3 headings.
  function buildToc(container) {
    var heads = container.querySelectorAll('h2, h3');
    if (heads.length < 3) return;                 // not worth a TOC
    var used = {};
    var items = [];
    heads.forEach(function (h) {
      var base = slugify(h.textContent) || 'section';
      var id = base, k = 2;
      while (used[id]) { id = base + '-' + (k++); }
      used[id] = true;
      h.id = id;
      items.push({ level: h.tagName === 'H3' ? 3 : 2, id: id, text: h.textContent });
    });
    var links = items.map(function (it) {
      return '<li class="toc__item toc__item--h' + it.level + '">' +
             '<a href="#' + it.id + '">' + escapeHtml(it.text) + '</a></li>';
    }).join('');
    var nav = document.createElement('nav');
    nav.className = 'toc';
    nav.setAttribute('aria-label', 'Table of contents');
    nav.innerHTML = '<p class="toc__title">On this page</p><ul class="toc__list">' + links + '</ul>';
    container.insertBefore(nav, container.firstChild);
  }

  function slugify(s) {
    return s.toLowerCase().trim()
      .replace(/[^\\w\\s-]/g, '')
      .replace(/[\\s_]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
})();
</script>"""


def build_protocol(sec_name: str, item: dict, sections) -> str:
    slug, title = item["slug"], item["title"]
    kind, path = source_for(slug)
    trailing = ""

    if kind == "md":
        # The page ships as a lightweight shell; the markdown is fetched and
        # rendered in the browser, so editing content/<slug>.md and redeploying
        # updates the page with no site rebuild.
        inner = (
            f'<div id="md-content" class="md-loading" '
            f'data-src="../content/{slug}.md">Loading protocol&hellip;</div>'
        )
        trailing = md_render_scripts(slug)
    elif kind == "html":
        inner = path.read_text(encoding="utf-8")
    elif kind == "rtf":
        inner = rtf_to_fragment(path)
    else:
        inner = f"""<div class="placeholder-note">
  {PLACEHOLDER_ICON}
  <div>
    <strong>Placeholder page.</strong> The full protocol has not been published yet.
    To publish it, drop the source document into <code>content/</code> as
    <code>{slug}.md</code> (Markdown, rendered live), or <code>{slug}.html</code> /
    <code>{slug}.rtf</code>, then re-run <code>generate.py</code>.
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
</div></main>
{trailing}"""
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
