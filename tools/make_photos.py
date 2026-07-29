#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""あみさん提供写真をWeb配信用WebP/JPEGへ決定的に変換する。

既定入力: ~/Downloads
既定出力: <repo>/assets/photos

品質は WebP=80 / JPEG=78 を固定し、120,000 bytes の上限を守るまで
長辺ではなく表示基準の幅を段階的に縮小する。1200px は上限であり、
細部量の多い写真では容量上限を優先して実幅が小さくなる。
"""

from __future__ import annotations

import argparse
import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, features


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = Path.home() / "Downloads"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "assets" / "photos"
TARGET_WIDTH = 1200
MIN_WIDTH = 360
MAX_BYTES = 120_000
WIDTH_STEP = 0.92
WEBP_QUALITY = 80
JPEG_QUALITY = 78


@dataclass(frozen=True)
class PhotoSpec:
    source: str
    output_stem: str


PHOTO_SPECS = (
    PhotoSpec("S__5242910_0.jpg", "tobinoko_1"),
    PhotoSpec("S__5242911_0.jpg", "tobinoko_2"),
    PhotoSpec("S__5242914_0.jpg", "yamanokami_1"),
    PhotoSpec("S__5242915_0.jpg", "yamanokami_2"),
    PhotoSpec("S__5242918_0.jpg", "takimichi_1"),
    PhotoSpec("S__5242919_0.jpg", "takimichi_2"),
    PhotoSpec("S__5242921.jpg", "sakanoue_1"),
)


def resized(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    if image.width == width:
        return image.copy()
    return image.resize((width, height), Image.Resampling.LANCZOS)


def encode_pair(image: Image.Image) -> tuple[bytes, bytes]:
    webp = io.BytesIO()
    image.save(webp, "WEBP", quality=WEBP_QUALITY, method=6, exif=b"")

    jpeg = io.BytesIO()
    image.save(
        jpeg,
        "JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
        subsampling="4:2:0",
        exif=b"",
    )
    return webp.getvalue(), jpeg.getvalue()


def fit_to_budget(image: Image.Image) -> tuple[Image.Image, bytes, bytes]:
    width = min(TARGET_WIDTH, image.width)
    while width >= MIN_WIDTH:
        candidate = resized(image, width)
        webp, jpeg = encode_pair(candidate)
        if len(webp) <= MAX_BYTES and len(jpeg) <= MAX_BYTES:
            return candidate, webp, jpeg
        next_width = min(width - 1, int(width * WIDTH_STEP))
        candidate.close()
        width = next_width
    raise RuntimeError(
        f"容量上限を満たせません: source={image.size}, min_width={MIN_WIDTH}, "
        f"max_bytes={MAX_BYTES}"
    )


def atomic_write(destination: Path, payload: bytes) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)


def convert(spec: PhotoSpec, source_dir: Path, output_dir: Path) -> str:
    source = source_dir / spec.source
    if not source.is_file():
        raise FileNotFoundError(f"入力写真がありません: {source}")

    with Image.open(source) as raw:
        prepared = ImageOps.exif_transpose(raw).convert("RGB")
        output_image, webp, jpeg = fit_to_budget(prepared)

    webp_path = output_dir / f"{spec.output_stem}.webp"
    jpeg_path = output_dir / f"{spec.output_stem}.jpg"
    atomic_write(webp_path, webp)
    atomic_write(jpeg_path, jpeg)
    result = (
        f"{spec.source} -> {spec.output_stem} "
        f"{output_image.width}x{output_image.height} "
        f"webp={len(webp)}B(q{WEBP_QUALITY}) "
        f"jpeg={len(jpeg)}B(q{JPEG_QUALITY})"
    )
    output_image.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if not features.check("webp"):
        raise RuntimeError("このPillowにはWebPサポートがありません")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for spec in PHOTO_SPECS:
        print(convert(spec, args.source_dir, args.output_dir))
    print(f"generated={len(PHOTO_SPECS) * 2} max_bytes={MAX_BYTES} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
