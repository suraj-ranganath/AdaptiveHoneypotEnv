#!/usr/bin/env bash
# Rebuild docs/figures/architecture.{svg,pdf,png} from architecture.tex.
set -euo pipefail

cd "$(dirname "$0")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pdflatex -halt-on-error -interaction=nonstopmode -output-directory "$tmp" architecture.tex
cp "$tmp/architecture.pdf" architecture.pdf
pdftocairo -png -r 300 -singlefile architecture.pdf architecture
# PDF keeps the white page. dvisvgm has no bgcolor flag; convert the PDF so the
# SVG canvas is opaque on GitHub's dark theme.
dvisvgm --pdf --bbox=papersize --font-format=woff2 --zoom=1.35 \
  -o architecture.svg architecture.pdf

python3 - << 'PY'
from PIL import Image
src = Image.open("architecture.png").convert("RGB")
canvas = Image.new("RGB", (3000, 2000), "white")
# Fit inside the 3:2 frame with a small margin.
scale = min(3000 * 0.94 / src.width, 2000 * 0.92 / src.height)
resized = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.Resampling.LANCZOS)
x = (3000 - resized.width) // 2
y = (2000 - resized.height) // 2
canvas.paste(resized, (x, y))
canvas.save("architecture-3x2.png", optimize=True)
print(f"3x2 {resized.size} on 3000x2000")
PY

echo "Wrote $(pwd)/architecture.svg"
echo "Wrote $(pwd)/architecture.pdf"
echo "Wrote $(pwd)/architecture.png"
echo "Wrote $(pwd)/architecture-3x2.png"
