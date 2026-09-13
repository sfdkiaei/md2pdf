#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persian Markdown -> PDF, right-to-left, with mermaid diagrams rendered.

    ./md2pdf.py report.md
    ./md2pdf.py report.md -o out.pdf --subtitle "نسخه ۱٫۰"

Why a browser and not a word processor: direction is declared once here, on
<html dir="rtl">, and every rule is written in logical properties, so the
browser's bidi implementation does the work. A .docx has to carry four separate
RTL switches, each of which Word silently ignores when it sits at the wrong
position in the XML — which is how a document ends up half right-to-left.

Mermaid blocks are rendered in that same browser pass, so diagrams land in the
PDF as vector SVG rather than bitmaps.

Requires: python3, node >= 22, and Chrome/Chromium/Edge (set CHROME_PATH to
point at a specific one).
"""
import argparse
import base64
import html as H
import mimetypes
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MERMAID_JS = os.path.join(HERE, "assets", "mermaid.min.js")
RENDER_JS = os.path.join(HERE, "render.mjs")

FONT_STACK = ("'IRANSans','IRANSansWeb','IRANSansX','Vazirmatn','B Nazanin',"
              "'Geeza Pro',Tahoma,sans-serif")
MONO_STACK = "'Menlo','Consolas','DejaVu Sans Mono',monospace"


# ─────────────────────────── stylesheet ──────────────────────────────────────
def stylesheet(margins):
    return """
@page { size: A4; margin: %(margins)s; }

:root{
  --ink:#1a2230; --muted:#5a6373; --accent:#1f3964; --accent-soft:#33538a;
  --rule:#dde3ea; --band:#f4f7fa; --code-bg:#f5f7f9;
}
*{ box-sizing:border-box; }
html{ direction:rtl; }
body{
  font-family:%(font)s; font-size:10.5pt; line-height:1.95; color:var(--ink);
  margin:0; text-align:justify; text-justify:inter-word;
}

/* Latin technical tokens stay LTR and unbreakable inside Persian text.
   Without the isolation, 2026-09-13 renders as 13-09-2026: the digits are
   LTR but the hyphens are bidi-neutral, so the groups get reordered. */
code, .ltr{ direction:ltr; unicode-bidi:isolate; }
code{
  font-family:%(mono)s; font-size:0.88em; background:var(--code-bg);
  border:1px solid var(--rule); border-radius:3px; padding:0.05em 0.35em;
  white-space:nowrap;
}

h1,h2,h3,h4{ color:var(--accent); line-height:1.6; text-align:start;
             break-after:avoid; page-break-after:avoid; }
h1{ font-size:19pt; margin:0 0 2mm; }
h2{ font-size:14pt; margin:11mm 0 3mm; padding-bottom:1.6mm;
    border-bottom:1.6pt solid var(--accent); }
h3{ font-size:11.5pt; margin:7mm 0 2mm; color:var(--accent-soft); }
h4{ font-size:10.5pt; margin:5mm 0 1.5mm; color:var(--accent-soft); }

p{ margin:0 0 2.6mm; }
strong{ font-weight:700; color:#101826; }
em{ font-style:italic; }
del{ color:var(--muted); }
a{ color:var(--accent-soft); text-decoration:none; }

ul,ol{ margin:0 0 3mm; padding-inline-start:6.5mm; }
li{ margin-bottom:1.4mm; }
li::marker{ color:var(--accent); font-weight:700; }
ol{ list-style:persian; }        /* Persian numerals, matching the headings */

blockquote{
  margin:0 0 3.5mm; padding:2.6mm 4mm; background:var(--band);
  border-inline-start:2.4pt solid var(--accent-soft); border-radius:2px;
}
blockquote p:last-child{ margin-bottom:0; }

table{
  width:100%%; border-collapse:collapse; margin:1mm 0 5mm; font-size:9.5pt;
  /* Long tables flow across pages instead of jumping whole and leaving a
     third of the previous page blank. */
  break-inside:auto;
}
thead{ display:table-header-group; }   /* header repeats on continuation */
tr{ break-inside:avoid; }
th,td{ border:0.6pt solid var(--rule); padding:1.8mm 2.4mm;
       text-align:start; vertical-align:top; }
th{ background:var(--accent); color:#fff; font-weight:700; text-align:center; }
tbody tr:nth-child(even) td{ background:var(--band); }

figure{ margin:3mm 0 5mm; text-align:center; break-inside:avoid; }
figure img, figure svg{ max-width:100%%; height:auto; }
figcaption{ color:var(--muted); font-size:9pt; margin-top:1.5mm; }

/* Mermaid lays out left-to-right; only the labels inside are Persian, and the
   browser shapes those correctly on its own. */
.mermaid{ direction:ltr; text-align:center; break-inside:avoid;
          margin:3mm 0 5mm; }
.mermaid svg{ max-width:100%%; height:auto; }

pre{
  background:var(--code-bg); border:0.6pt solid var(--rule); border-radius:3px;
  padding:3mm 4mm; margin:0 0 4mm; direction:ltr; text-align:left;
  font-family:%(mono)s; font-size:8.5pt; line-height:1.55;
  white-space:pre-wrap; break-inside:avoid;
}
pre code{ background:none; border:0; padding:0; white-space:pre-wrap; }

hr{ border:0; border-top:0.8pt solid var(--rule); margin:7mm 0; }

.cover{ text-align:center; margin-bottom:9mm; }
.cover h1{ font-size:25pt; margin-bottom:2.5mm; }
.cover .sub{ color:var(--muted); font-size:12pt; padding-bottom:5mm;
             border-bottom:1.6pt solid var(--rule); }
.meta{ margin-bottom:8mm; text-align:start; }
.meta p{ margin-bottom:1.6mm; }
""" % {"margins": margins, "font": FONT_STACK, "mono": MONO_STACK}


# ─────────────────────────── inline markdown ─────────────────────────────────
INLINE = re.compile(
    r"(!\[[^\]]*\]\([^)]+\)"        # image
    r"|\*\*.+?\*\*"                 # bold
    r"|__.+?__"
    r"|(?<!\*)\*[^*\n]+\*(?!\*)"    # italic
    r"|~~.+?~~"                     # strikethrough
    r"|`[^`]+`"                     # code
    r"|\[[^\]]+\]\([^)]+\))")       # link

# An ASCII token glued together by neutral separators: a date, a path, a
# version, an identifier. Persian-Indic digits are deliberately not matched —
# they are bidi class AN and already resolve correctly.
LTR_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-_./:@+][A-Za-z0-9]+)+[-_./:@+]?")


def data_uri(path, base_dir):
    full = path if os.path.isabs(path) else os.path.join(base_dir, path)
    if not os.path.exists(full):
        return None
    mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
    with open(full, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


def plain(text):
    """Escape, then isolate Latin tokens so bidi cannot reorder their pieces."""
    return LTR_TOKEN.sub(lambda m: '<span class="ltr">%s</span>' % m.group(0),
                         H.escape(text))


def inline(text, base_dir):
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", part)
        if m:
            uri = data_uri(m.group(2), base_dir)
            out.append('<img src="%s" alt="%s">' % (uri, H.escape(m.group(1)))
                       if uri else plain(m.group(1)))
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append("<strong>%s</strong>" % plain(part[2:-2]))
        elif part.startswith("__") and part.endswith("__"):
            out.append("<strong>%s</strong>" % plain(part[2:-2]))
        elif part.startswith("~~") and part.endswith("~~"):
            out.append("<del>%s</del>" % plain(part[2:-2]))
        elif part.startswith("`") and part.endswith("`"):
            out.append("<code>%s</code>" % H.escape(part[1:-1]))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append("<em>%s</em>" % plain(part[1:-1]))
        else:
            m = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)
            out.append(plain(m.group(1)) if m else plain(part))
    return "".join(out)


# ─────────────────────────── block markdown ──────────────────────────────────
def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_body(md_text, base_dir, subtitle, cover):
    lines = md_text.split("\n")
    body, i, first_h1, frontmatter, has_mermaid = [], 0, True, False, False

    while i < len(lines):
        raw, s = lines[i], lines[i].strip()
        if not s:
            i += 1
            continue

        # fenced block
        if s.startswith("```") or s.startswith("~~~"):
            fence, lang, buf = s[:3], s[3:].strip(), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1
            if lang.lower() == "mermaid":
                has_mermaid = True
                body.append('<pre class="mermaid">%s</pre>'
                            % H.escape("\n".join(buf)))
            else:
                body.append("<pre><code>%s</code></pre>"
                            % H.escape("\n".join(buf)))
            continue

        # table
        if s.startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            head = split_row(s)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip()))
                i += 1
            t = ["<table><thead><tr>"]
            t += ["<th>%s</th>" % inline(c, base_dir) for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(
                    "<td>%s</td>" % inline(r[j] if j < len(r) else "", base_dir)
                    for j in range(len(head))) + "</tr>")
            t.append("</tbody></table>")
            body.append("".join(t))
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = min(len(m.group(1)), 4)
            if lvl == 1 and first_h1 and cover:
                first_h1 = False
                body.append('<div class="cover"><h1>%s</h1>%s</div>' % (
                    inline(m.group(2), base_dir),
                    '<div class="sub">%s</div>' % inline(subtitle, base_dir)
                    if subtitle else ""))
                body.append('<div class="meta">')
                frontmatter = True
            else:
                first_h1 = False
                body.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2), base_dir), lvl))
            i += 1
            continue

        # horizontal rule — also closes the cover's metadata block
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            if frontmatter:
                body.append("</div>")
                frontmatter = False
            body.append("<hr>")
            i += 1
            continue

        # blockquote
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q = lines[i].strip().lstrip(">").strip()
                if q:
                    buf.append(q[2:].strip() if q.startswith("- ") else q)
                i += 1
            body.append("<blockquote>%s</blockquote>"
                        % "".join("<p>%s</p>" % inline(b, base_dir) for b in buf))
            continue

        # list (one level; nested items fold into the parent item)
        mb = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", raw)
        if mb:
            tag = "ul" if mb.group(2)[0] in "-*+" else "ol"
            items = []
            while i < len(lines):
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if not mm or ("ul" if mm.group(2)[0] in "-*+" else "ol") != tag:
                    break
                items.append("<li>%s</li>" % inline(mm.group(3), base_dir))
                i += 1
            body.append("<%s>%s</%s>" % (tag, "".join(items), tag))
            continue

        body.append("<p>%s</p>" % inline(s, base_dir))
        i += 1

    if frontmatter:
        body.append("</div>")
    return "".join(body), has_mermaid


READY_SCRIPT = """
<script>
(async () => {
  try {
    if (window.mermaid) {
      mermaid.initialize({
        startOnLoad: false, theme: 'neutral', securityLevel: 'loose',
        fontFamily: %(font)s,
        flowchart: { useMaxWidth: true, htmlLabels: true },
        sequence: { useMaxWidth: true, wrap: true },
      });
      await mermaid.run({ querySelector: '.mermaid' });
    }
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
  } catch (e) {
    console.error('diagram rendering failed:', e);
  }
  // The renderer waits on this flag, so a diagram is never printed half-drawn.
  window.__READY__ = true;
})();
</script>
"""


def build_html(md_path, subtitle, margins, cover):
    base_dir = os.path.dirname(os.path.abspath(md_path))
    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()
    body, has_mermaid = markdown_to_body(md_text, base_dir, subtitle, cover)

    scripts = ""
    if has_mermaid:
        if not os.path.exists(MERMAID_JS):
            sys.exit("error: mermaid bundle missing at %s" % MERMAID_JS)
        with open(MERMAID_JS, encoding="utf-8") as f:
            scripts += "<script>%s</script>" % f.read()
    scripts += READY_SCRIPT % {"font": '"%s"' % FONT_STACK.replace('"', "'")}

    return ("<!doctype html><html lang=\"fa\" dir=\"rtl\"><head>"
            "<meta charset=\"utf-8\"><style>%s</style></head>"
            "<body>%s%s</body></html>"
            % (stylesheet(margins), body, scripts))


def find_node():
    """Locate Node >= 22. A version manager keeps node out of a non-login
    shell's PATH, so PATH alone is not enough to go on."""
    candidates = [os.environ.get("NODE"), "node"]
    for root in ("~/.nvm/versions/node", "~/.local/share/fnm/node-versions"):
        base = os.path.expanduser(root)
        if os.path.isdir(base):
            # Newest first, so a stale old install does not win.
            for v in sorted(os.listdir(base), reverse=True):
                candidates.append(os.path.join(base, v, "bin", "node"))
                candidates.append(os.path.join(base, v, "installation", "bin", "node"))
    candidates += [
        os.path.expanduser("~/.volta/bin/node"),
        "/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node",
    ]

    for c in candidates:
        if not c:
            continue
        try:
            r = subprocess.run([c, "-e", "process.stdout.write(process.versions.node)"],
                               capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and int(r.stdout.split(".")[0] or 0) >= 22:
            return c
    sys.exit("error: Node >= 22 not found. Install it, or set NODE=/path/to/node.\n"
             "       (The PDF step drives Chrome through Node's built-in WebSocket.)")


def main():
    ap = argparse.ArgumentParser(
        description="Render a Persian Markdown file to a right-to-left PDF.")
    ap.add_argument("input", help="path to the .md file")
    ap.add_argument("-o", "--output",
                    help="output .pdf (default: alongside the input)")
    ap.add_argument("-s", "--subtitle", default=None,
                    help="subtitle shown under the first heading")
    ap.add_argument("--margins", default="18mm 16mm 20mm 16mm",
                    help="CSS @page margin (default: '18mm 16mm 20mm 16mm')")
    ap.add_argument("--no-cover", action="store_true",
                    help="treat the first heading as an ordinary heading")
    ap.add_argument("--keep-html", action="store_true",
                    help="keep the intermediate .html next to the output")
    ap.add_argument("--timeout", type=int, default=60000,
                    help="ms to wait for diagrams to draw (default: 60000)")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit("error: no such file: %s" % args.input)
    out = args.output or os.path.splitext(args.input)[0] + ".pdf"

    html = build_html(args.input, args.subtitle, args.margins, not args.no_cover)

    if args.keep_html:
        html_path = os.path.splitext(out)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
    else:
        fd, html_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html)

    try:
        subprocess.run([find_node(), RENDER_JS, html_path, out,
                        str(args.timeout)], check=True)
    except subprocess.CalledProcessError as e:
        sys.exit("error: PDF rendering failed (exit %d)." % e.returncode)
    finally:
        if not args.keep_html:
            os.unlink(html_path)


if __name__ == "__main__":
    main()
