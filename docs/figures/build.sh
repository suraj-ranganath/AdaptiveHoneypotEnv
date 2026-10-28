#!/usr/bin/env bash
# Rebuild docs/figures/architecture.{svg,pdf,png} from architecture.tex.
set -euo pipefail

cd "$(dirname "$0")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pdflatex -halt-on-error -interaction=nonstopmode -output-directory "$tmp" architecture.tex
cp "$tmp/architecture.pdf" architecture.pdf
pdftocairo -png -r 200 -singlefile architecture.pdf architecture
# PDF keeps the white page. dvisvgm has no bgcolor flag; convert the PDF so the
# SVG canvas is opaque on GitHub's dark theme.
dvisvgm --pdf --bbox=papersize --font-format=woff2 --zoom=1.35 \
  -o architecture.svg architecture.pdf

echo "Wrote $(pwd)/architecture.svg"
echo "Wrote $(pwd)/architecture.pdf"
echo "Wrote $(pwd)/architecture.png"
