#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
VENV="$ROOT/.venv"
TESTBED="$ROOT/testbed/photo_folder"
export ROOT

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

. "$VENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "$ROOT"

mkdir -p "$TESTBED/inbox" "$TESTBED/nested/birds"

python - <<'PY'
import os
from pathlib import Path

from PIL import Image, ImageDraw

root = Path(os.environ["ROOT"]) / "testbed" / "photo_folder"

def make_sample(path: Path, pattern: str) -> None:
    image = Image.new("RGB", (512, 320), "white")
    draw = ImageDraw.Draw(image)
    if pattern == "grid":
        for x in range(0, 512, 16):
            draw.line((x, 0, x, 319), fill="black", width=1)
        for y in range(0, 320, 16):
            draw.line((0, y, 511, y), fill="black", width=1)
    elif pattern == "diag":
        for offset in range(-320, 512, 20):
            draw.line((max(0, offset), max(0, -offset), min(511, 511 + offset), min(319, 319 - offset)), fill="black", width=2)
    else:
        draw.rectangle((96, 64, 416, 256), outline="black", width=6)
        draw.ellipse((176, 96, 336, 256), outline="black", width=6)
    exif = image.getexif()
    exif[271] = "Nikon"
    exif[272] = "NIKON Z 8"
    exif[42035] = "Nikon"
    exif[42036] = "NIKKOR Z 70-200mm f/2.8 VR S"
    exif[37386] = (200, 1)
    exif[33437] = (28, 10)
    image.save(path, quality=95, exif=exif.tobytes())

make_sample(root / "inbox" / "nikon_sample_01.jpg", "grid")
(root / "inbox" / "nikon_sample_02.NEF").write_bytes(b"NEF sample bytes")
make_sample(root / "nested" / "birds" / "bird_burst_01.JPG", "diag")
(root / "nested" / "birds" / "bird_burst_02.NEF").write_bytes(b"NEF burst bytes")
(root / "ignore.txt").write_text("not a photo", encoding="utf-8")
PY

cat <<EOF
Testbed hazır.

Kullanım:
  . "$VENV/bin/activate"
  firfoto show-config
  firfoto scan "$TESTBED" --recursive
  firfoto analyze "$TESTBED" --recursive --category bird --db "$ROOT/testbed/firfoto.sqlite3" --json

İlk deneme klasörü:
  $TESTBED
EOF
