# -*- coding: utf-8 -*-
"""圆头像尺寸/位置候选对比：真头裁切 + 真背景 + 字幕带/按钮区标注。

用法: python size_options.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layout as L
import compose_final as CF

SAMPLE = Path(r"C:\Users\benhu\Desktop\档案001\预览\12-圆头像试样.mp4")
SRC = HERE.parent / "02-剪辑" / "03-超分.mp4"
OUT = Path(r"C:\Users\benhu\Desktop\档案001\预览\16-圆尺寸三档.png")
FONT = r"C:\Windows\Fonts\msyh.ttc"

# (标签, 直径, 圆心x, 圆心y)
CANDS = [
    ("现在", 220, 860, 1390),
    ("A", 260, 845, 1420),
    ("B", 280, 840, 1435),
]


def main() -> int:
    # 背景：成片里 S12 中间某帧（已经压好动画）
    bgp = HERE / "preview" / "sz_bg.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", "55", "-i", str(SAMPLE), "-frames:v", "1",
                    "-update", "1", str(bgp)], check=True)
    bg = Image.open(bgp).convert("RGB")

    # 人物帧（同一时间点的原始素材）
    pp = HERE / "preview" / "sz_person.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", "147.5", "-i", str(SRC), "-frames:v", "1",
                    "-update", "1", str(pp)], check=True)
    person = Image.open(pp).convert("RGB")

    tiles = []
    for tag, d, cx, cy in CANDS:
        dest = (cx - d // 2, cy - d // 2, cx + d // 2, cy + d // 2)
        crop = (L.HEAD_CX - L.HEAD_BOX // 2, L.HEAD_CY - L.HEAD_BOX // 2,
                L.HEAD_CX + L.HEAD_BOX // 2, L.HEAD_CY + L.HEAD_BOX // 2)
        layer, (lx, ly) = CF.person_card(person, crop, dest, d // 2, L.PIP_FEATHER)
        im = bg.convert("RGBA")
        im.alpha_composite(layer, (lx, ly))
        im = im.convert("RGB")

        dr = ImageDraw.Draw(im, "RGBA")
        dr.rectangle([0, L.SUBTITLE_BAND[0], L.W, L.SUBTITLE_BAND[1]],
                     outline=(255, 200, 0, 170), width=3)
        dr.rectangle([950, 1080, L.W, 1700], fill=(255, 0, 0, 26),
                     outline=(255, 60, 60, 160), width=2)
        dr.rectangle([0, 0, L.W, 56], fill=(0, 0, 0, 165))
        dr.text((14, 12),
                f"{tag}  d={d} @({cx},{cy})  右距 {L.W - cx - d // 2}  下距 {L.H - cy - d // 2}",
                font=ImageFont.truetype(FONT, 30), fill=(255, 235, 120, 245))
        tiles.append(im.resize((360, 640), Image.LANCZOS))

    sheet = Image.new("RGB", (368 * len(tiles) - 8, 640), (12, 16, 24))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 368, 0))
    sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.LANCZOS)
    sheet.save(OUT)
    print("saved", OUT, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
