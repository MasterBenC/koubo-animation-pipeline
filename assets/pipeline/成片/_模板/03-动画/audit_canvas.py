# -*- coding: utf-8 -*-
"""验收④：每场动画实际占了多少画布（内容外接框 + 画布利用率）。

判据（和 `版式规范.md` / `pipeline.md` 里的数字是同一套，改这里就要改文档）：
    宽占 ≥ 80%   —— 对内容区宽 936 取比值，低于 80% 就是「还是窄版式」
    下沿 ≥ 1150  —— 低于 1150 会被读成「上面一坨、下面空了」

用法: python audit_canvas.py
      python audit_canvas.py s03 s07
"""
from __future__ import annotations

import sys

import numpy as np

import _paths

_paths.ensure_import_path()

import scene_kit as K       # noqa: E402

MIN_WIDTH = 0.80
MIN_BOTTOM = 1150
CONTENT_W = 936.0


def main() -> int:
    keys = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = _paths.discover_scenes()
    if keys:
        files = [p for p in files if _paths.matches(p, keys)]

    bg = np.asarray(K.canvas(0).finish().convert("RGB")).astype(np.int16)
    rows = []
    for p in files:
        mod = _paths.load_scene(p)
        dur = _paths.duration(mod)
        x0s, y0s, x1s, y1s = [], [], [], []
        for i in range(9):
            t = dur * i / 8.0 - 0.01
            a = np.asarray(mod.frame(max(0.0, min(t, dur - 0.01))).convert("RGB")).astype(np.int16)
            d = np.abs(a - bg).max(axis=2) > 10
            x0, y0, x1, y1 = K.scrim_box()
            d[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = False   # 顶部薄膜不算内容
            ys, xs = np.nonzero(d)
            if len(xs) < 50:
                continue
            x0s.append(xs.min()); x1s.append(xs.max())
            y0s.append(ys.min()); y1s.append(ys.max())
        if not x0s:
            print(f"[空  ] {p.name} 没画出任何内容（和背景逐像素相同）")
            continue
        bx0, bx1 = min(x0s), max(x1s)
        by0, by1 = min(y0s), max(y1s)
        rows.append((p.stem, bx0, bx1, by0, by1, (bx1 - bx0) / CONTENT_W, by1))

    print(f"{'场景':26} {'x 范围':>13} {'y 范围':>13}  {'宽占':>5} {'下沿':>5}")
    for r in rows:
        print(f"{r[0]:26} {r[1]:5d}-{r[2]:5d} {r[3]:5d}-{r[4]:5d}  {r[5]*100:4.0f}% {r[4]:5d}")

    narrow = [r[0] for r in rows if r[5] < MIN_WIDTH]
    low = [r[0] for r in rows if r[4] < MIN_BOTTOM]
    print(f"\n宽度不足 {MIN_WIDTH*100:.0f}%（还是窄版）：{len(narrow)} 场 -> {', '.join(narrow) or '无'}")
    print(f"下沿不到 {MIN_BOTTOM}（下半屏空）：{len(low)} 场 -> {', '.join(low) or '无'}")
    return 0 if not narrow and not low else 1


if __name__ == "__main__":
    raise SystemExit(main())
