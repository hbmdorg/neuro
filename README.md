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

A protocol page is built from the first source it finds in `content/`, matched
to the protocol's slug:

1. **`content/<slug>.rtf`** — the simplest path. In Word, *Save As → Rich Text
   Format (.rtf)* and drop the file in `content/` named after the slug. On
   re-generation its structure (headings, bold/italic, bullet and numbered
   lists, tables) is converted to HTML while its own fonts and colours are
   discarded so the site stylesheet controls the look.
2. **`content/<slug>.html`** — a hand-authored HTML fragment (body content only,
   no `<html>`/`<head>` wrapper). Use this when you want full control; it takes
   precedence over an `.rtf` of the same slug.

Then run `python3 generate.py`. The placeholder is replaced by the real content
and the home-page card loses its "Draft" badge.

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
