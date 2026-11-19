# -*- coding: utf-8 -*-
"""合成一张「构图验收图」：成片真实画面 + 圆头像 + 字幕带 + 安全区标注。

用法: python make_check_png.py <成片帧.png> <输出.png>

字体走 `motion.font()`（和动画同一套回退链），不再自己写死 `C:\\Windows\\Fonts`。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

import _paths

_paths.ensure_import_path()

import layout as L      # noqa: E402
import motion           # noqa: E402


def font(size: int):
    for name in ("yh_b", "yh", "noto_b", "noto"):
        try:
            return motion.font(name, size)
        except Exception:
            continue
    from PIL import ImageFont
    return ImageFont.load_default()


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    im = Image.open(src).convert("RGB").resize((L.W, L.H), Image.LANCZOS)
    d = ImageDraw.Draw(im, "RGBA")
    f = font(30)
    fb = font(42)

    # 安全区
    s = L.SAFE
    d.rectangle([s["left"], s["top"], L.W - s["right"], L.H - s["bottom"]],
                outline=(0, 200, 255, 150), width=3)
    d.text((s["left"] + 8, s["top"] + 6),
           f"安全区 {s['left']},{s['top']} - {L.W - s['right']},{L.H - s['bottom']}",
           font=f, fill=(0, 200, 255, 235))

    # 标题层
    tb0, tb1 = L.TITLE_BAND
    d.rectangle([L.CONTENT[0], tb0, L.CONTENT[2], tb1],
                outline=(255, 160, 0, 200), width=2)
    d.text((L.CONTENT[0] + 8, tb0 - 30), f"标题层 {tb0}-{tb1}", font=f,
           fill=(255, 180, 60, 235))

    # 字幕带
    b0, b1 = L.SUBTITLE_BAND
    d.rectangle([0, b0, L.W, b1], fill=(255, 200, 0, 40), outline=(255, 200, 0, 210), width=3)
    d.text((16, b0 + 96), f"字幕带 {b0}-{b1}（后期烧，动画层不得进入）", font=f,
           fill=(255, 210, 60, 245))

    # 圆头像（互切模式没有）
    if L.PIP_R > 0:
        d.ellipse([L.PIP[0], L.PIP[1], L.PIP[2], L.PIP[3]], outline=(255, 60, 60, 235), width=4)
        d.line([(L.PIP_CX, L.PIP[1] - 34), (L.PIP_CX, L.PIP[3] + 34)],
               fill=(255, 60, 60, 200), width=2)
        d.line([(L.PIP[0] - 34, L.PIP_CY), (L.PIP[2] + 34, L.PIP_CY)],
               fill=(255, 60, 60, 200), width=2)
        d.text((40, L.PIP[3] + 42), f"圆 d={L.PIP_W} @ ({L.PIP_CX},{L.PIP_CY})",
               font=f, fill=(255, 90, 90, 245))
        d.text((40, L.PIP[3] + 82),
               f"右距 {L.W - L.PIP[2]}  下距 {L.H - L.PIP[3]}  与字幕带重叠 "
               f"{max(0, L.SUBTITLE_BAND[1] - L.PIP[1])}px（既定设计）",
               font=f, fill=(255, 90, 90, 245))

    # 内容格
    c0, c1, c2, c3 = L.CONTENT
    d.rectangle([c0, c1, c2, c3], outline=(120, 255, 160, 170), width=3)
    d.text((c0 + 8, c1 + 6), f"内容区 {c2 - c0}×{c3 - c1}", font=f, fill=(120, 255, 160, 235))

    d.text((L.W // 2 - 230, 60), f"构图验收 · {L.W}×{L.H} · {L.ACTIVE_PROFILE}",
           font=fb, fill=(255, 255, 255, 245))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
