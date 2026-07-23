"""Generate print-ready QR assets for the Nakayama guide map."""

from __future__ import annotations

import math
from pathlib import Path

import segno


TARGET_URL = "https://lightaim-hub.github.io/nakayama-guidemap/"
ERROR_CORRECTION = "m"
QUIET_ZONE_MODULES = 4
MIN_PNG_SIDE_PX = 1200
SVG_SCALE = 10

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = REPO_ROOT / "assets"
SVG_PATH = ASSETS_DIR / "qr_guidemap.svg"
PNG_PATH = ASSETS_DIR / "qr_guidemap_print.png"


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    qr = segno.make_qr(
        TARGET_URL,
        error=ERROR_CORRECTION,
        boost_error=False,
    )
    side_modules, _ = qr.symbol_size(scale=1, border=QUIET_ZONE_MODULES)
    png_scale = math.ceil(MIN_PNG_SIDE_PX / side_modules)

    qr.save(
        SVG_PATH,
        kind="svg",
        scale=SVG_SCALE,
        border=QUIET_ZONE_MODULES,
        dark="#000",
        light="#fff",
        xmldecl=True,
        svgns=True,
        title="なかやま商店街ガイドマップ QRコード",
    )
    qr.save(
        PNG_PATH,
        kind="png",
        scale=png_scale,
        border=QUIET_ZONE_MODULES,
        dark="#000",
        light="#fff",
        dpi=300,
    )

    png_side = side_modules * png_scale
    print(
        f"Generated {SVG_PATH.relative_to(REPO_ROOT)} and "
        f"{PNG_PATH.relative_to(REPO_ROOT)} "
        f"(QR {qr.designator}, border={QUIET_ZONE_MODULES}, "
        f"PNG={png_side}x{png_side}px)"
    )


if __name__ == "__main__":
    main()
