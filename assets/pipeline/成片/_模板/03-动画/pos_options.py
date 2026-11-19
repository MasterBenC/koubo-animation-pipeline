# -*- coding: utf-8 -*-
"""圆头像「位置」三档对比图：真帧打底，叠候选圆心 + 字幕带 + 平台按钮区。

参数类决策给图不给话——一次出 3 档真图给用户选，不要用文字描述让他脑补。

用法:
    python pos_options.py --video <成片或超分.mp4> --out 预览/圆心三档.png
    python pos_options.py --video a.mp4 --at 60 --offsets "0,0;20,30;40,60"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import _paths

_paths.ensure_import_path()

import layout as L  # noqa: E402
import motion        # noqa: E402

BUTTON_BOX = (950, 1080, 1080, 1700)   # 抖音右侧按钮区大致范围


def grab(video: Path, at: float, out: Path) -> Image.Image:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1",
                    "-update", "1", str(out)], check=True)
    return Image.open(out).convert("RGB").resize((L.W, L.H), Image.LANCZOS)


def parse_offsets(spec: str) -> list[tuple[int, int]]:
    out = []
    for piece in spec.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        dx, _, dy = piece.partition(",")
        out.append((int(float(dx or 0)), int(float(dy or 0))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="抽底图的视频（成片/超分/原片都行）")
    ap.add_argument("--at", type=float, default=60.0, help="抽帧时间点（秒）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--offsets", default="0,0;20,30;40,60",
                    help="相对当前圆心的偏移，分号分隔，例如 0,0;20,30")
    args = ap.parse_args()

    base = grab(Path(args.video), args.at, Path(args.out).with_name("_pos_base.png"))
    r = L.PIP_R
    tiles = []
    for i, (dx, dy) in enumerate(parse_offsets(args.offsets)):
        cx, cy = L.PIP_CX + dx, L.PIP_CY + dy
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        d.rectangle(BUTTON_BOX, fill=(255, 0, 0, 28), outline=(255, 60, 60, 190), width=3)
        d.text((956, 1088), "按钮区", font=motion.font("yh", 24), fill=(255, 90, 90, 235))
        d.rectangle([0, L.SUBTITLE_BAND[0], L.W, L.SUBTITLE_BAND[1]],
                    outline=(255, 200, 0, 190), width=3)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 60, 60, 240), width=4)
        d.line([(cx, cy - r - 26), (cx, cy + r + 26)], fill=(255, 60, 60, 170), width=2)
        d.line([(cx - r - 26, cy), (cx + r + 26, cy)], fill=(255, 60, 60, 170), width=2)
        tag = "现在" if (dx, dy) == (0, 0) else "ABCDEFG"[min(i, 6)]
        label = f"{tag}  ({cx},{cy})  右距 {L.W - cx - r}  下距 {L.H - cy - r}"
        d.rectangle([0, 0, L.W, 52], fill=(0, 0, 0, 150))
        d.text((16, 10), label, font=motion.font("yh_b", 30), fill=(255, 235, 120, 245))
        tiles.append(im.resize((360, 640), Image.LANCZOS))

    sheet = Image.new("RGB", (368 * len(tiles) - 8, 640), (12, 16, 24))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 368, 0))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
