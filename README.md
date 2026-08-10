# Neuro Anesthesia Protocols

Static website of neuroanesthesia protocols, hosted on GitHub Pages at
**https://hbmd.org**.

Pages are generated from a plain-text list of protocols by `generate.py`. Each
protocol currently renders as a placeholder; once a Word document is converted
to HTML it can be dropped in and re-published without touching the layout.

## Project layout

```
neuro-site/
├── generate.py         # the site generator
├── protocols.txt       # the list of protocols (edit this)
├── content/            # optional HTML fragments, one per protocol slug
├── assets/
│   ├── style.css
│   ├── neurons.svg     # header/hero image — replace with the supplied art
│   └── favicon.svg
├── index.html          # generated
├── protocols/          # generated, one <slug>.html per protocol
├── CNAME               # custom domain (hbmd.org)
└── .nojekyll           # serve files as-is on GitHub Pages
```

`index.html` and everything in `protocols/` are **generated** — do not edit them
by hand; edit `protocols.txt` (and the fragments in `content/`) and re-run.

## Regenerating the site

```bash
python3 generate.py            # uses protocols.txt
python3 generate.py other.txt  # or a different input file
```

The generator rebuilds `index.html`, the shared header/menu, and one page per
protocol. Removing a protocol from the input and re-running deletes its page.

## Adding a protocol

Add a line to `protocols.txt`. Group protocols into menu dropdowns with
`== Section ==` headers:

```
== Cranial ==
Awake Craniotomy
Aneurysm Clipping / Subarachnoid Hemorrhage | aneurysm-sah
```

The optional `| slug` after a title fixes the filename and content-fragment
name; otherwise a slug is derived from the title.

## Publishing real content

A protocol page is built from the highest-precedence source it finds in
`content/`, matched to the protocol's slug:

1. **`content/<slug>.md`** — Markdown, **rendered live in the browser**. When a
   `.md` exists it wins and nothing else is considered. The generated page is a
   thin shell that fetches the markdown and renders it client-side (marked.js +
   DOMPurify). This means you can edit the protocol text and redeploy *just the
   markdown file* — no `generate.py` run needed — and it also lets you use the
   full range of Markdown/HTML formatting.
2. **`content/<slug>.html`** — a hand-authored HTML fragment (body content only,
   no `<html>`/`<head>` wrapper), embedded at build time.
3. **`content/<slug>.rtf`** — In Word, *Save As → Rich Text Format (.rtf)* and
   drop it in `content/`. On generation its structure (headings, bold/italic,
   bullet and numbered lists, tables) is converted to HTML while its own fonts
   and colours are discarded so the site stylesheet controls the look.

Run `python3 generate.py` to (re)build pages. The placeholder is replaced by the
real content and the home-page card loses its "Draft" badge.

> **Note on Markdown pages:** because the markdown is fetched over HTTP, a
> markdown page shows its content on the published site (or via a local server
> such as `python3 -m http.server`), but **not** when the `.html` file is opened
> directly from disk (`file://`) — browsers block the fetch. HTML and RTF
> sources are embedded at build time and preview fine from disk.

RTF conversion uses macOS `textutil` (built in) or LibreOffice `soffice`/
`libreoffice` when available, falling back to a lightweight built-in parser.
For the richest results (real headings, nested lists, tables) run it on a Mac
or a machine with LibreOffice installed.

## Replacing the header image

Drop the supplied "two neurons connecting" image into `assets/` and either name
it `neurons.svg` (overwriting the placeholder) or update `HEADER_IMAGE` near the
top of `generate.py` to point at the new filename (e.g. `assets/neurons.png`),
then re-run the generator.

## Deploying to GitHub Pages

1. Push this folder to a GitHub repository.
2. Repo **Settings → Pages** → Source: *Deploy from a branch* → branch `main`,
   folder `/ (root)`.
3. The `CNAME` file points the site at `hbmd.org`; add the matching DNS records
   (an `ALIAS`/`A` records to GitHub's IPs for the apex domain, or a `CNAME`
   record if you use a `www`/subdomain) at your DNS provider, then enable
   *Enforce HTTPS*.
