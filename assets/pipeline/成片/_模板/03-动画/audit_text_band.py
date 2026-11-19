# -*- coding: utf-8 -*-
"""验收⑥：文字落区（画面里的字只许待在允许框里）。

为什么需要它：字幕带（竖屏默认 y 1300–1460）是用户后期自己烧字幕的地方，
画面里任何一个字进去都会被盖住；而标题层又贴着内容区上沿，改个字号就顶出去了。
① check_layout 查图形/卡片越界、③ audit_band 只查字幕带、② check_text 查"字压字"，
都不查"字有没有出上下左右四条边"——这道补的就是它。

原理：`motion.text_tracking()` 打开后，每次 `c.text()` 都会把（文本, 包围盒）
记进 `motion.TEXT_BOXES`；逐场按 fps 采样跑 `frame(t)`，把所有 alpha > 0.05 的
文字框跟允许框比一次。

允许框（默认取 layout.py，改版式只改 layout，这里自动跟着变）：
    x  L.CONTENT[0] .. L.CONTENT[2]     默认 72 .. 1008
    y  L.SAFE["top"] .. L.CONTENT[3]    默认 140 .. 1290

用法:
    python audit_text_band.py                 # 全部场景
    python audit_text_band.py s03 s07         # 只查指定场次（大小写不敏感）
    python audit_text_band.py --fps 2         # 采密一点
"""
from __future__ import annotations

import argparse
import sys

import _paths

_paths.ensure_import_path()

import layout as L          # noqa: E402
import motion               # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="只查这些场次（s03 / S03 / s03_xxx）")
    ap.add_argument("--fps", type=float, default=1.0, help="采样帧率，默认 1（静置文字够用）")
    ap.add_argument("--top", type=int, default=L.SAFE["top"])
    ap.add_argument("--bottom", type=int, default=L.CONTENT[3])
    ap.add_argument("--left", type=int, default=L.CONTENT[0])
    ap.add_argument("--right", type=int, default=L.CONTENT[2])
    a = ap.parse_args(argv[1:])

    files = _paths.discover_scenes()
    if a.only:
        files = [p for p in files if _paths.matches(p, a.only)]
    if not files:
        print("[!] 没有匹配的场景文件（只认 sNN_*.py）")
        return 1

    bad = 0
    for p in files:
        mod = _paths.load_scene(p)
        dur = _paths.duration(mod)
        t, worst = 0.0, []
        while t < dur:
            with motion.text_tracking() as boxes:
                mod.frame(t)
                for box in list(boxes):
                    if box["a"] <= 0.05 or not box["t"].strip():
                        continue
                    x0, y0, x1, y1 = box["box"]
                    if y0 < a.top or y1 > a.bottom or x0 < a.left or x1 > a.right:
                        worst.append((round(t, 2), box["t"], [round(v) for v in box["box"]]))
            t += 1.0 / a.fps
        if worst:
            bad += len(worst)
            print(f"[!! ] {p.stem}: {len(worst)} 处越界")
            for w in worst[:4]:
                print(f"       t={w[0]}s 「{w[1]}」 box={w[2]}")
        else:
            print(f"[OK ] {p.stem}")

    print(f"\n越界合计 {bad} 处"
          f"（允许区 y {a.top}-{a.bottom} / x {a.left}-{a.right}，"
          f"字幕带 {L.SUBTITLE_BAND[0]}-{L.SUBTITLE_BAND[1]} 不进）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
