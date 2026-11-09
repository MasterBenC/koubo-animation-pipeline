# -*- coding: utf-8 -*-
"""每场动画实际占了多少画布：内容外接框 + 画布利用率。

用来判断哪些场次还是"窄版式"（当年给矩形画中画排的），需要重排。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import layout as L
import scene_kit as K

SKIP = {"demo_ledger.py"}


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    bg = np.asarray(K.canvas(0).finish().convert("RGB")).astype(np.int16)
    rows = []
    for p in sorted((HERE / "scenes").glob("*.py")):
        if p.name in SKIP:
            continue
        mod = load(p)
        dur = float(getattr(mod, "DURATION", 10.0))
        x0s, y0s, x1s, y1s = [], [], [], []
        for i in range(9):
            t = dur * i / 8.0 - 0.01
            a = np.asarray(mod.frame(max(0.0, min(t, dur - 0.01))).convert("RGB")).astype(np.int16)
            d = np.abs(a - bg).max(axis=2) > 10
            ys, xs = np.nonzero(d)
            if len(xs) < 50:
                continue
            x0s.append(xs.min()); x1s.append(xs.max())
            y0s.append(ys.min()); y1s.append(ys.max())
        if not x0s:
            continue
        bx0, bx1 = min(x0s), max(x1s)
        by0, by1 = min(y0s), max(y1s)
        rows.append((p.stem, bx0, bx1, by0, by1,
                     (bx1 - bx0) / 936.0, (by1 - by0) / 890.0))
    print(f"{'场景':26} {'x 范围':>13} {'y 范围':>13}  {'宽占':>5} {'高占':>5}")
    for r in rows:
        print(f"{r[0]:26} {r[1]:5d}-{r[2]:5d} {r[3]:5d}-{r[4]:5d}  {r[5]*100:4.0f}% {r[6]*100:4.0f}%")
    narrow = [r[0] for r in rows if r[5] < 0.80]
    low = [r[0] for r in rows if r[4] < 1150]
    print(f"\n宽度不足 80%（还是窄版）：{len(narrow)} 场 -> {', '.join(narrow)}")
    print(f"下沿不到 1150（下半屏空）：{len(low)} 场 -> {', '.join(low)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
