**English** • [فارسی](README.fa.md)

# md2pdf

Renders a Persian Markdown file to a right-to-left PDF: IRANSans, justified
text, styled tables, and mermaid diagrams drawn as vector graphics.

```bash
md2pdf report.md                                  # -> report.pdf
md2pdf report.md -o out.pdf -s "نسخه ۱٫۰ — گزارش تحویل"
```

Output defaults to the input path with a `.pdf` extension.

## Supported systems

| OS | Status |
|---|---|
| macOS | Supported and tested (Apple Silicon and Intel) |
| Linux | Supported — same code paths; Chrome/Chromium found in the usual places |
| Windows | Use **WSL** and follow the Linux instructions |

The entry point is a POSIX `sh` script, so on Windows it needs WSL or Git Bash.
Under Git Bash you can also call `python md2pdf.py …` directly; Chrome and Edge
are looked for in `C:/Program Files/…` as well.

## Install

```bash
./install.sh                 # checks requirements, then links into ~/.local/bin
./install.sh /usr/local/bin  # or somewhere already on PATH
./install.sh --check         # only report on requirements, change nothing
```

It links rather than copies, so pulling updates here updates the command too.
Running `./md2pdf` directly from this folder works without installing.

**`install.sh` never installs anything for you.** Python, Node and Chrome are
system-wide packages with their own upgrade paths, and a document tool is the
wrong thing to be silently putting a browser on your machine. It checks what is
present and prints the command for your OS for whatever is not:

```
md2pdf — checking requirements (macos)

  [ ok ] Python    3.13.7 (/opt/homebrew/bin/python3.13)
  [MISS] Node      Node 22+ not found
         brew install node   (or use nvm / volta; or set NODE=/path/to/node)
  [ ok ] Chrome    /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  [warn] IRANSans  not found — falling back to Vazirmatn / B Nazanin / Tahoma
```

It exits non-zero when a required item is missing, but still creates the link,
so installing the dependency later is all that is left to do. IRANSans is a
warning rather than an error: the stylesheet falls back, and the PDF is still
produced — it just does not look as intended, which is the kind of failure
worth being told about.

## Options

| Option | Meaning |
|---|---|
| `-o, --output` | Output path (default: input name with `.pdf`) |
| `-s, --subtitle` | Subtitle under the first heading |
| `--no-cover` | Treat the first `#` as an ordinary heading, not a cover title |
| `--margins` | CSS `@page` margin (default `18mm 16mm 20mm 16mm`) |
| `--keep-html` | Keep the intermediate HTML next to the output, for debugging |
| `--timeout` | Milliseconds to wait for diagrams (default 60000) |

## Requirements

| Need | Notes |
|---|---|
| Python 3.8+ | The wrapper probes for a working one; override with `PYTHON=…` |
| Node 22+ | Found on `PATH`, under `~/.nvm`, or via `NODE=…` |
| Chrome / Chromium / Edge | Override with `CHROME_PATH=…` |
| IRANSans | Optional; falls back to Vazirmatn → B Nazanin → Geeza Pro → Tahoma |

No `npm install`: the PDF step drives Chrome over the DevTools Protocol using
Node's built-in WebSocket, and `assets/mermaid.min.js` is vendored, so the tool
works offline.

## Markdown supported

Headings (`#`–`####`), paragraphs, **bold**, *italic*, `code`, ~~strike~~,
links, images, `-`/`1.` lists, `>` blockquotes, `|` tables, `---` rules, fenced
code blocks, and ```` ```mermaid ```` diagrams.

The first `#` becomes a cover title; everything between it and the first `---`
is treated as a metadata block — left ragged rather than justified, because
justifying two lines that contain one long filename stretches them across the
page. Use `--no-cover` for documents without a title page.

## Why a browser rather than a .docx

Direction is declared once, on `<html dir="rtl">`, and every layout rule is
written in logical properties (`margin-inline`, `text-align:start`), so nothing
has to be mirrored by hand and the browser's bidi implementation does the work.

A `.docx` carries four separate RTL switches — `w:bidi` on the section, `w:bidi`
on each paragraph, `w:rtl` on each run, `w:bidiVisual` on each table — and
WordprocessingML property containers are `xsd:sequence`, so Word **silently
ignores** any of them placed at the wrong position in the XML. That is how a
document ends up looking right in one viewer and half left-to-right in Word.

## Two details worth knowing

**Latin tokens are bidi-isolated.** In an RTL paragraph the digits of
`2026-09-13` are left-to-right but the hyphens are bidi-neutral, so without
isolation the groups get reordered and the date renders as `13-09-2026` — a
different day. Tokens glued by `-_./:@+` are wrapped in an isolating span.
Persian-Indic digits are deliberately left alone: they are bidi class AN and
already resolve correctly.

**Diagrams render in the same browser pass.** Mermaid blocks are drawn in the
page before printing, so they land in the PDF as vector SVG rather than
bitmaps, and there is no separate `mermaid-cli` step. Mermaid lays out
left-to-right; only its labels are Persian, and the browser shapes those
correctly on its own.

## Layout

```
md2pdf/
├── md2pdf              entry point (sh): resolves symlinks, picks a Python
├── md2pdf.py           Markdown -> RTL HTML, then calls the renderer
├── render.mjs          HTML -> PDF via Chrome DevTools Protocol, no npm deps
├── install.sh          symlink onto PATH
└── assets/
    └── mermaid.min.js  vendored, so diagrams work offline
```
