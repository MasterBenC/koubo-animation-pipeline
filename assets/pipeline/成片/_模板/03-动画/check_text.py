# -*- coding: utf-8 -*-
"""逐帧检查"文字压文字"。

思路：给 motion.Canvas 打开 TRACK，每次画字都会记下（文本, 包围盒）。
把每个场景按 10fps 跑一遍，两两比较包围盒，相交面积超过小字框 35% 就报。

用法：
    python check_text.py                 # 全部场景
    python check_text.py s12 s14         # 只查指定的
    python check_text.py --fps 20 --verbose
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "scripts"))

import motion  # noqa: E402
from motion import TEXT_BOXES  # noqa: E402


def _on_canvas(b, w=1080, h=1920):
    return b[2] > 0 and b[3] > 0 and b[0] < w and b[1] < h


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def load(name: str):
    return importlib.import_module(f"scenes.{name}")


def scan(name: str, fps: float, ratio: float, min_px: float, verbose: bool):
    mod = load(name)
    dur = float(mod.DURATION)
    hits = []
    t = 0.0
    while t < dur:
        TEXT_BOXES.clear()
        try:
            mod.frame(t)
        except Exception as exc:                      # 某帧炸了不影响整体
            print(f"  [ERR] {name} @{t:.2f}s {exc!r}")
            t += 1.0 / fps
            continue
        boxes = [b for b in TEXT_BOXES if b["a"] > 0.06 and b["t"].strip()]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                A, B = boxes[i], boxes[j]
                ia = inter(A["box"], B["box"])
                # 画到画布外的字（滑动入场的起始位置）本来就看不见，不算重叠
                if not _on_canvas(A["box"]) or not _on_canvas(B["box"]):
                    continue
                if ia <= 0:
                    continue
                small = min(area(A["box"]), area(B["box"]))
                if small <= 0:
                    continue
                # 同一段文字被重画（阴影/描边/重复调用）：文本相同且几乎重合，跳过
                if A["t"] == B["t"] and ia / small > 0.6:
                    continue
                # 一个框被另一个完全包住且文本是包含关系（"1.5万亿" 与 "万亿"）
                if A["t"] in B["t"] or B["t"] in A["t"]:
                    if ia / small > 0.75:
                        continue
                if ia / small >= ratio and ia >= min_px:
                    hits.append((t, A, B, ia / small))
        t += 1.0 / fps

    # 同一对文字连续出现，合并成一个区间
    merged = []
    for t, A, B, r in hits:
        key = (A["t"], B["t"])
        if merged and merged[-1]["key"] == key and t - merged[-1]["t1"] <= 1.2 / fps + 1e-6:
            merged[-1]["t1"] = t
            merged[-1]["r"] = max(merged[-1]["r"], r)
        else:
            merged.append({"key": key, "t0": t, "t1": t, "r": r,
                           "a": A["box"], "b": B["box"]})
    return merged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*")
    ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--ratio", type=float, default=0.35)
    ap.add_argument("--min-px", type=float, default=900)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    import layout as L
    names = args.scenes or [s[1] for s in L.SCENE_SLOTS]
    motion.TRACK[0] = True
    total = 0
    for name in names:
        hits = scan(name, args.fps, args.ratio, args.min_px, args.verbose)
        if not hits:
            print(f"[OK ] {name:24s} 无文字重叠")
            continue
        total += len(hits)
        print(f"[!! ] {name:24s} {len(hits)} 处")
        for h in hits:
            a, b = h["key"]
            print(f"      {h['t0']:6.2f}-{h['t1']:6.2f}s  重叠{h['r']*100:3.0f}%  "
                  f"「{a}」x{h['a'][0]:.0f}-{h['a'][2]:.0f} y{h['a'][1]:.0f}-{h['a'][3]:.0f}  ×  "
                  f"「{b}」x{h['b'][0]:.0f}-{h['b'][2]:.0f} y{h['b'][1]:.0f}-{h['b'][3]:.0f}")
    print(f"\n合计 {total} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
