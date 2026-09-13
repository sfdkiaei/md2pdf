#!/bin/sh
# Link md2pdf onto PATH so it can be run from any directory.
#
#   ./install.sh              -> ~/.local/bin/md2pdf
#   ./install.sh /usr/local/bin
#
# A symlink rather than a copy: the tool keeps working from wherever this
# checkout lives, and `git pull` here updates the installed command too.
set -e

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN=${1:-$HOME/.local/bin}

mkdir -p "$BIN"
ln -sf "$HERE/md2pdf" "$BIN/md2pdf"
echo "linked $BIN/md2pdf -> $HERE/md2pdf"

case ":$PATH:" in
  *":$BIN:"*) echo "$BIN is already on PATH." ;;
  *) echo
     echo "$BIN is not on PATH yet. Add it, e.g.:"
     echo "  echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.zshrc && exec zsh" ;;
esac
