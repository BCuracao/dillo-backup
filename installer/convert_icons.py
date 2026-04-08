"""Convert dillo-logo.png into platform-specific icon files.

Outputs:
  - installer/assets/dillo.ico   (Windows: 16–256px multi-size)
  - installer/assets/dillo.icns  (macOS:   16–512px @1x/@2x)

Also copies dillo.ico into installer/ so Inno Setup and PyInstaller
can reference it without path changes.

Usage:
  python installer/convert_icons.py
"""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = PROJECT_ROOT / "frontend" / "public" / "dillo-logo-color.png"
ASSETS_DIR = PROJECT_ROOT / "installer" / "assets"
INSTALLER_DIR = PROJECT_ROOT / "installer"

ICO_SIZES = [16, 32, 48, 64, 128, 256]
ICNS_TYPES = {
    16: b"icp4",   # 16x16
    32: b"icp5",   # 32x32
    64: b"icp6",   # 64x64 (ic12 is 32x32@2x but icp6 is 64x64)
    128: b"ic07",  # 128x128
    256: b"ic08",  # 256x256
    512: b"ic09",  # 512x512
}


def create_ico(source: Image.Image, dest: Path) -> None:
    """Save a multi-size .ico file.

    Pillow's ICO plugin accepts a ``sizes`` list and will downsample
    the source image for each entry automatically.
    """
    source.save(
        dest,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
    )
    print(f"  OK {dest}  ({', '.join(f'{s}px' for s in ICO_SIZES)})")


def _pack_icns_entry(icon_type: bytes, png_data: bytes) -> bytes:
    """Pack a single ICNS icon entry: 4-byte type + 4-byte length + data."""
    length = 8 + len(png_data)
    return icon_type + struct.pack(">I", length) + png_data


def create_icns(source: Image.Image, dest: Path) -> None:
    """Build an .icns file from PNG data entries.

    Apple's ICNS format stores each size as a type-tagged chunk.
    Since macOS 10.7+ the chunks can contain raw PNG data, which
    is what we use here (no need for the legacy ARGB packing).
    """
    entries = b""
    sizes_written: list[int] = []

    for size, icon_type in sorted(ICNS_TYPES.items()):
        img = source.copy().resize((size, size), Image.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp, format="PNG")
            tmp_path = Path(tmp.name)
        png_data = tmp_path.read_bytes()
        tmp_path.unlink()
        entries += _pack_icns_entry(icon_type, png_data)
        sizes_written.append(size)

    total_length = 8 + len(entries)
    icns_data = b"icns" + struct.pack(">I", total_length) + entries

    dest.write_bytes(icns_data)
    print(f"  OK {dest}  ({', '.join(f'{s}px' for s in sizes_written)})")


def main() -> None:
    if not LOGO_PATH.exists():
        raise FileNotFoundError(f"Source logo not found: {LOGO_PATH}")

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Source: {LOGO_PATH}")
    source = Image.open(LOGO_PATH).convert("RGBA")
    print(f"  Original size: {source.size[0]}x{source.size[1]}")

    ico_path = ASSETS_DIR / "dillo.ico"
    create_ico(source, ico_path)

    icns_path = ASSETS_DIR / "dillo.icns"
    create_icns(source, icns_path)

    # Copy .ico to installer/ root for Inno Setup / PyInstaller references
    installer_ico = INSTALLER_DIR / "dillo.ico"
    installer_ico.write_bytes(ico_path.read_bytes())
    print(f"  OK {installer_ico}  (copy for Inno Setup)")

    print("\nDone — all icons generated.")


if __name__ == "__main__":
    main()
