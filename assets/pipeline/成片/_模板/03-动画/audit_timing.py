# -*- coding: utf-8 -*-
"""台词 vs 动画节拍 对齐审计。

原理：逐帧算画面变化量（相邻帧差异像素数），尖峰 = 动画出现了一个新东西；
把尖峰时间和台词起点摆在同一张表上，就能一眼看出谁早谁晚。

用法:
    python audit_timing.py s03 s05          # 只看这两场
    python audit_timing.py                  # 全部 16 场
    python audit_timing.py s05 --fps 20
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import layout as L

CUES = HERE.parent / "02-剪辑" / "cues.json"
SKIP = {"demo_ledger.py"}


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def events(mod, dur: float, fps: float, thresh: float = 900.0, gap: float = 0.28):
    """返回 [(t, 变化像素数)]，只保留显著尖峰。"""
    n = int(dur * fps)
    prev = np.asarray(mod.frame(0.0).convert("L")).astype(np.int16)
    raw = []
    for i in range(1, n + 1):
        t = i / fps
        cur = np.asarray(mod.frame(min(t, dur - 0.01)).convert("L")).astype(np.int16)
        d = int((np.abs(cur - prev) > 6).sum())
        raw.append((round(t, 3), d))
        prev = cur
    # 局部极大 + 最小间隔
    out = []
    for idx, (t, d) in enumerate(raw):
        if d < thresh:
            continue
        lo = max(0, idx - 2)
        hi = min(len(raw), idx + 3)
        if d < max(x[1] for x in raw[lo:hi]):
            continue
        if out and t - out[-1][0] < gap:
            if d > out[-1][1]:
                out[-1] = (t, d)
            continue
        out.append((t, d))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix", nargs="*")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--thresh", type=float, default=900.0)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    cues = json.loads(CUES.read_text(encoding="utf-8"))
    rows = []

    for pid, (sid, stem, t0, t1, dur) in enumerate(L.SCENE_SLOTS):
        if args.prefix and not any(stem.startswith(p) or sid.lower() == p.lower()
                                   for p in args.prefix):
            continue
        p = HERE / "scenes" / f"{stem}.py"
        if not p.exists():
            continue
        mod = load(p)
        ev = events(mod, dur, args.fps, args.thresh)
        local_cues = [
            (round(max(0.0, c["start"] - t0), 2), round(min(dur, c["end"] - t0), 2), c["text"])
            for c in cues if c["end"] > t0 and c["start"] < t1
        ]
        rows.append(dict(scene=sid, stem=stem, dur=dur, cues=local_cues,
                         events=[[t, d] for t, d in ev]))

        print(f"\n{'=' * 74}\n{sid}  {stem}   时长 {dur:.2f}s")
        print(f"{'视觉事件':>10}   {'台词':<6} 内容")
        merged = [("EV", t, d) for t, d in ev] + [("CUE", c[0], c[2]) for c in local_cues]
        merged.sort(key=lambda x: (x[1], 0 if x[0] == "CUE" else 1))
        for kind, t, val in merged:
            if kind == "EV":
                print(f"{t:9.2f}s   [动效] 变化 {val}px")
            else:
                print(f"{t:9.2f}s   台词   {val}")

    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
