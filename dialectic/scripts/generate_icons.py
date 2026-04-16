"""Generate platform icon artifacts (.icns, .ico) from assets/icon.png.

Reads a 512x512 source PNG and emits:
    assets/Dialectic.icns   (macOS — via iconutil when available, else Pillow fallback)
    assets/dialectic.ico    (Windows — via Pillow multi-resolution ICO)

Runnable on macOS, Windows, and Linux (falls back to pure-Pillow .icns
assembly when iconutil is not present).
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("Pillow is required. Install with: pip install Pillow\n")
    sys.exit(1)


APP_NAME = "Dialectic"
ROOT = Path(__file__).resolve().parent.parent
SRC_PNG = ROOT / "assets" / "icon.png"
ICNS_OUT = ROOT / "assets" / f"{APP_NAME}.icns"
ICO_OUT = ROOT / "assets" / f"{APP_NAME.lower()}.ico"


# (size, scale, filename) — Apple's expected iconset entries.
ICNS_VARIANTS = [
    (16, 1, "icon_16x16.png"),
    (16, 2, "icon_16x16@2x.png"),
    (32, 1, "icon_32x32.png"),
    (32, 2, "icon_32x32@2x.png"),
    (128, 1, "icon_128x128.png"),
    (128, 2, "icon_128x128@2x.png"),
    (256, 1, "icon_256x256.png"),
    (256, 2, "icon_256x256@2x.png"),
    (512, 1, "icon_512x512.png"),
    (512, 2, "icon_512x512@2x.png"),
]


ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


# OSType codes for .icns entries (pure-Python fallback only).
# See https://en.wikipedia.org/wiki/Apple_Icon_Image_format
ICNS_OSTYPES = {
    (16, 1): b"icp4",
    (16, 2): b"ic11",
    (32, 1): b"icp5",
    (32, 2): b"ic12",
    (128, 1): b"ic07",
    (128, 2): b"ic13",
    (256, 1): b"ic08",
    (256, 2): b"ic14",
    (512, 1): b"ic09",
    (512, 2): b"ic10",
}


def _resize(src: Image.Image, pixels: int) -> Image.Image:
    return src.resize((pixels, pixels), Image.LANCZOS)


def _write_iconset(src: Image.Image, iconset_dir: Path) -> None:
    iconset_dir.mkdir(parents=True, exist_ok=True)
    for size, scale, name in ICNS_VARIANTS:
        pixels = size * scale
        _resize(src, pixels).save(iconset_dir / name, format="PNG")


def _build_icns_with_iconutil(src: Image.Image, out_path: Path) -> bool:
    if shutil.which("iconutil") is None:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / f"{APP_NAME}.iconset"
        _write_iconset(src, iconset)
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(out_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            sys.stderr.write(f"iconutil failed: {result.stderr}\n")
            return False
    return True


def _build_icns_pure_python(src: Image.Image, out_path: Path) -> None:
    """Assemble a minimal .icns by concatenating PNG entries with OSType headers."""
    entries = []
    for size, scale, _ in ICNS_VARIANTS:
        pixels = size * scale
        buf = tempfile.SpooledTemporaryFile()
        _resize(src, pixels).save(buf, format="PNG")
        buf.seek(0)
        data = buf.read()
        ostype = ICNS_OSTYPES[(size, scale)]
        entries.append(ostype + struct.pack(">I", 8 + len(data)) + data)

    payload = b"".join(entries)
    file_size = 8 + len(payload)
    with open(out_path, "wb") as f:
        f.write(b"icns" + struct.pack(">I", file_size) + payload)


def build_icns(src: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if _build_icns_with_iconutil(src, out_path):
        print(f"  icns (iconutil): {out_path}")
        return
    _build_icns_pure_python(src, out_path)
    print(f"  icns (pure-python): {out_path}")


def build_ico(src: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src.save(out_path, format="ICO", sizes=ICO_SIZES)
    print(f"  ico: {out_path}")


def main() -> int:
    if not SRC_PNG.exists():
        sys.stderr.write(f"Source icon not found: {SRC_PNG}\n")
        return 1

    src = Image.open(SRC_PNG).convert("RGBA")
    if src.size[0] < 512 or src.size[1] < 512:
        sys.stderr.write(
            f"Warning: source is {src.size}, recommend at least 512x512.\n"
        )

    print(f"Generating icons for {APP_NAME} from {SRC_PNG}")
    build_icns(src, ICNS_OUT)
    build_ico(src, ICO_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
