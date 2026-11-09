# -*- coding: utf-8 -*-
"""圆头像右下移位的三档对比图。

底图用成片真实一帧，叠三种圆心位置 + 抖音右侧按钮区警示框。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layout as L

SAMPLE = Path(r"C:\Users\benhu\Desktop\档案001\预览\12-圆头像试样.mp4")
OUT = Path(r"C:\Users\benhu\Desktop\档案001\预览\15-圆心三档.png")

CANDS = [
    ("A", 850, 1360),
    ("B", 860, 1390),
    ("C", 880, 1420),
]
R = L.PIP_R
FONT = r"C:\Windows\Fonts\msyh.ttc"


def main() -> int:
    frame = HERE / "preview" / "pos_base.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", "60", "-i", str(SAMPLE), "-frames:v", "1",
                    "-update", "1", str(frame)], check=True)

    base = Image.open(frame).convert("RGB")
    tiles = []
    for tag, cx, cy in CANDS:
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        # 抖音右侧按钮区（点赞/评论/收藏/分享大致范围）
        d.rectangle([950, 1080, 1080, 1700], fill=(255, 0, 0, 28),
                    outline=(255, 60, 60, 190), width=3)
        d.text((956, 1088), "按钮区", font=ImageFont.truetype(FONT, 24),
               fill=(255, 90, 90, 235))
        # 字幕带
        d.rectangle([0, L.SUBTITLE_BAND[0], L.W, L.SUBTITLE_BAND[1]],
                    outline=(255, 200, 0, 190), width=3)
        # 候选圆
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(255, 60, 60, 240), width=4)
        d.line([(cx, cy - R - 26), (cx, cy + R + 26)], fill=(255, 60, 60, 170), width=2)
        d.line([(cx - R - 26, cy), (cx + R + 26, cy)], fill=(255, 60, 60, 170), width=2)
        label = f"{tag}  ({cx},{cy})  右距 {L.W - cx - R}  下距 {L.H - cy - R}"
        d.rectangle([0, 0, L.W, 52], fill=(0, 0, 0, 150))
        d.text((16, 10), label, font=ImageFont.truetype(FONT, 30),
               fill=(255, 235, 120, 245))
        tiles.append(im.resize((360, 640), Image.LANCZOS))

    sheet = Image.new("RGB", (360 * len(tiles) + 8 * (len(tiles) - 1), 640), (12, 16, 24))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 368, 0))
    sheet.save(OUT)
    print("saved", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
