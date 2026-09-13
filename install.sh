#!/bin/sh
# Link md2pdf onto PATH, after checking that what it needs is present.
#
#   ./install.sh                 -> ~/.local/bin/md2pdf
#   ./install.sh /usr/local/bin
#   ./install.sh --check         only report on requirements, install nothing
#
# This script NEVER installs anything for you. Python, Node and Chrome are
# system-wide packages with their own upgrade paths, and a document tool is the
# wrong thing to be silently putting a browser on your machine. What it does
# instead is tell you exactly what is missing and the command for your OS.
#
# A symlink rather than a copy: the tool keeps working from wherever this
# checkout lives, and `git pull` here updates the installed command too.

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN=""
CHECK_ONLY=0

for arg in "$@"; do
  case $arg in
    -c|--check) CHECK_ONLY=1 ;;
    -h|--help)
      # Print the header comment, stopping at the first line that is not one,
      # so the help text cannot drift out of sync with a fixed line number.
      sed -n '2,${/^#/!q;s/^# \{0,1\}//;p;}' "$0"
      exit 0 ;;
    -*) echo "install.sh: unknown option: $arg" >&2; exit 2 ;;
    *)  BIN=$arg ;;
  esac
done
[ -n "$BIN" ] || BIN=$HOME/.local/bin

case $(uname -s) in
  Darwin) OS=macos ;;
  Linux)  OS=linux ;;
  *)      OS=other ;;
esac

MISSING=0
ok()   { printf '  [ ok ] %-9s %s\n' "$1" "$2"; }
warn() { printf '  [warn] %-9s %s\n' "$1" "$2"; }
bad()  { printf '  [MISS] %-9s %s\n' "$1" "$2"; MISSING=$((MISSING + 1)); }
hint() { printf '         %s\n' "$1"; }

echo "md2pdf — checking requirements ($OS)"
echo

# ── Python 3.8+ ──────────────────────────────────────────────────────────────
PY=""
for c in "$PYTHON" python3.14 python3.13 python3.12 python3.11 python3.10 \
         python3.9 /usr/bin/python3 python3; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' \
       >/dev/null 2>&1; then PY=$c; break; fi
done
if [ -n "$PY" ]; then
  ok Python "$("$PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])') ($(command -v "$PY"))"
else
  bad Python "no working Python 3.8+ found"
  case $OS in
    macos) hint "brew install python@3.13   (or set PYTHON=/path/to/python3)" ;;
    linux) hint "sudo apt install python3   # or dnf/pacman equivalent" ;;
    *)     hint "install Python 3.8+, or set PYTHON=/path/to/python3" ;;
  esac
fi

# ── Node 22+ ─────────────────────────────────────────────────────────────────
NODE_BIN=""
NODE_CANDIDATES="$NODE node /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node"
[ -d "$HOME/.nvm/versions/node" ] && NODE_CANDIDATES="$NODE_CANDIDATES $(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null | sort -r)"
[ -x "$HOME/.volta/bin/node" ] && NODE_CANDIDATES="$NODE_CANDIDATES $HOME/.volta/bin/node"
for c in $NODE_CANDIDATES; do
  [ -n "$c" ] || continue
  v=$("$c" -e 'process.stdout.write(process.versions.node)' 2>/dev/null) || continue
  case ${v%%.*} in ''|*[!0-9]*) continue ;; esac
  [ "${v%%.*}" -ge 22 ] && { NODE_BIN=$c; NODE_VER=$v; break; }
done
if [ -n "$NODE_BIN" ]; then
  ok Node "$NODE_VER ($NODE_BIN)"
else
  bad Node "Node 22+ not found"
  case $OS in
    macos) hint "brew install node   (or use nvm / volta; or set NODE=/path/to/node)" ;;
    linux) hint "see https://nodejs.org/en/download — distro packages are often too old" ;;
    *)     hint "install Node 22+, or set NODE=/path/to/node" ;;
  esac
fi

# ── Chrome / Chromium / Edge ─────────────────────────────────────────────────
CHROME=""
for c in "$CHROME_PATH" \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium" \
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  /usr/bin/google-chrome /usr/bin/google-chrome-stable \
  /usr/bin/chromium /usr/bin/chromium-browser /snap/bin/chromium \
  /usr/bin/microsoft-edge /usr/bin/brave-browser; do
  [ -n "$c" ] && [ -x "$c" ] && { CHROME=$c; break; }
done
if [ -n "$CHROME" ]; then
  ok Chrome "$CHROME"
else
  bad Chrome "no Chrome/Chromium/Edge found"
  case $OS in
    macos) hint "brew install --cask google-chrome   (or set CHROME_PATH=…)" ;;
    linux) hint "sudo apt install chromium   # or google-chrome-stable" ;;
    *)     hint "install Chrome/Chromium/Edge, or set CHROME_PATH=…" ;;
  esac
fi

# ── IRANSans (soft requirement) ──────────────────────────────────────────────
# Not fatal: the stylesheet falls back. But a silent fallback is the worst kind
# of failure here — the PDF is produced and simply does not look as intended.
FONT_FOUND=0
case $OS in
  macos)
    for d in "$HOME/Library/Fonts" /Library/Fonts /System/Library/Fonts; do
      [ -d "$d" ] && ls "$d" 2>/dev/null | grep -qi '^IRANSans' && FONT_FOUND=1 && break
    done ;;
  linux)
    command -v fc-list >/dev/null 2>&1 && fc-list 2>/dev/null | grep -qi 'IRANSans' && FONT_FOUND=1 ;;
esac
if [ "$FONT_FOUND" -eq 1 ]; then
  ok IRANSans "installed"
elif [ "$OS" = other ]; then
  warn IRANSans "cannot check on this OS — install it for the intended look"
else
  warn IRANSans "not found — falling back to Vazirmatn / B Nazanin / Tahoma"
  hint "install the IRANSans family, or edit FONT_STACK in md2pdf.py"
fi

echo
if [ "$MISSING" -gt 0 ]; then
  echo "$MISSING required item(s) missing — md2pdf will not run until they are installed."
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
  exit $([ "$MISSING" -gt 0 ] && echo 1 || echo 0)
fi

# ── Link ─────────────────────────────────────────────────────────────────────
# Linked even when something is missing, so installing the dependency later is
# all that is left to do.
mkdir -p "$BIN" || exit 1
ln -sf "$HERE/md2pdf" "$BIN/md2pdf" || exit 1
echo "linked $BIN/md2pdf -> $HERE/md2pdf"

case ":$PATH:" in
  *":$BIN:"*) echo "$BIN is already on PATH." ;;
  *) echo
     echo "$BIN is not on PATH yet. Add it, e.g.:"
     echo "  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.zshrc && exec zsh" ;;
esac

exit $([ "$MISSING" -gt 0 ] && echo 1 || echo 0)
