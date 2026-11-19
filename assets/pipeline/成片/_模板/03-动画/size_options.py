# -*- coding: utf-8 -*-
"""圆头像「尺寸」三档对比：真头裁切 + 真背景 + 字幕带/按钮区标注。

用法:
    python size_options.py --person <03-超分.mp4> --bg <成片.mp4> --out 预览/圆尺寸三档.png
    python size_options.py --person p.mp4 --bg b.mp4 --sizes "220,260,280" --person-at 147.5

`--person` 给人物母版（未压动画的超分片），`--bg` 给要贴上去的那一帧的来源。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import _paths

_paths.ensure_import_path()

import compose_final as CF  # noqa: E402
import layout as L          # noqa: E402
import motion               # noqa: E402

BUTTON_BOX = (950, 1080, 1080, 1700)


def grab(video: Path, at: float, out: Path) -> Image.Image:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1",
                    "-update", "1", str(out)], check=True)
    return Image.open(out).convert("RGB").resize((L.W, L.H), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True, help="人物母版（03-超分.mp4）")
    ap.add_argument("--bg", required=True, help="背景帧来源（成片 04-合成.mp4 等）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="220,260,280", help="候选直径，逗号分隔")
    ap.add_argument("--person-at", type=float, default=0.0, help="从人物母版抽帧的时刻")
    ap.add_argument("--bg-at", type=float, default=0.0, help="从背景抽帧的时刻")
    args = ap.parse_args()

    tmp = Path(args.out).with_name("_size_tmp")
    bg = grab(Path(args.bg), args.bg_at, tmp / "bg.png")
    person = grab(Path(args.person), args.person_at, tmp / "person.png")

    crop = (L.HEAD_CX - L.HEAD_BOX // 2, L.HEAD_CY - L.HEAD_BOX // 2,
            L.HEAD_CX + L.HEAD_BOX // 2, L.HEAD_CY + L.HEAD_BOX // 2)
    tiles = []
    for i, raw in enumerate([s for s in args.sizes.split(",") if s.strip()]):
        d_px = int(float(raw))
        dest = (L.PIP_CX - d_px // 2, L.PIP_CY - d_px // 2,
                L.PIP_CX + d_px // 2, L.PIP_CY + d_px // 2)
        layer, (lx, ly) = CF.person_card(person, crop, dest, d_px // 2, L.PIP_FEATHER)
        im = bg.convert("RGBA")
        im.alpha_composite(layer, (lx, ly))
        im = im.convert("RGB")

        dr = ImageDraw.Draw(im, "RGBA")
        dr.rectangle([0, L.SUBTITLE_BAND[0], L.W, L.SUBTITLE_BAND[1]],
                     outline=(255, 200, 0, 170), width=3)
        dr.rectangle(BUTTON_BOX, fill=(255, 0, 0, 26), outline=(255, 60, 60, 160), width=2)
        dr.rectangle([0, 0, L.W, 56], fill=(0, 0, 0, 165))
        tag = "现在" if d_px == L.PIP_W else "ABCDEFG"[min(i, 6)]
        dr.text((14, 12),
                f"{tag}  d={d_px} @({L.PIP_CX},{L.PIP_CY})  "
                f"右距 {L.W - L.PIP_CX - d_px // 2}  下距 {L.H - L.PIP_CY - d_px // 2}",
                font=motion.font("yh_b", 30), fill=(255, 235, 120, 245))
        tiles.append(im.resize((360, 640), Image.LANCZOS))

    sheet = Image.new("RGB", (368 * len(tiles) - 8, 640), (12, 16, 24))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 368, 0))
    sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.LANCZOS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("saved", out, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
