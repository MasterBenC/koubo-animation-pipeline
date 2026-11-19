# -*- coding: utf-8 -*-
"""验收⑤：台词 vs 动画节拍 对齐审计。

原理：逐帧算画面变化量（相邻帧差异**像素个数**），尖峰 = 动画出现了一个新东西；
把尖峰时间和台词起点摆在同一张表上，就能一眼看出谁早谁晚。

`--thresh` 的单位是**变化像素个数**（1080×1920 画布上），不是帧、也不是秒：
    900（默认）  只看大动作（整块内容出现/翻页）
    60           连轻动作、呼吸、死区一起看（找"画面停了 6 秒"用这个）

台词表读 `<项目>/02-剪辑/cues.json`（成片时间轴，由 build_cues.py 生成）。

用法:
    python audit_timing.py s03 s05          # 只看这两场（大小写不敏感）
    python audit_timing.py                  # 全部场景
    python audit_timing.py s05 --fps 20 --thresh 60
    python audit_timing.py --json timing.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import _paths

_paths.ensure_import_path()

import layout as L  # noqa: E402

CUES = _paths.HERE.parent / "02-剪辑" / "cues.json"


def load_cues() -> list[dict]:
    if not CUES.exists():
        print(f"[!] 找不到台词表 {CUES}\n"
              "    先跑：python 管线/scripts/build_cues.py <项目>/02-剪辑/asr_verify/words.json "
              "-o <项目>/02-剪辑/cues.json")
        return []
    data = json.loads(CUES.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):          # 兼容 {"cues": [...]}
        data = data.get("cues", [])
    return data


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
    ap.add_argument("prefix", nargs="*", help="场景 s03 / S03 / s03_xxx")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--thresh", type=float, default=900.0, help="变化像素数阈值")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    cues = load_cues()
    rows = []

    slots = {stem.lower(): (sid, stem, t0, t1, dur) for sid, stem, t0, t1, dur in L.SCENE_SLOTS}
    if not slots:
        print("[!] layout.SCENE_SLOTS 是空的：节拍审计需要「场次 -> 起止时间」这张表。\n"
              "    装新片时把 SCENE_SLOTS 整块换成本片的场次表（见 references/schemas.md）。")
        return 2

    for p in _paths.discover_scenes():
        key = p.stem.lower()
        if key not in slots:
            print(f"[注] {p.name} 不在 layout.SCENE_SLOTS 里，跳过（先补场次表）")
            continue
        sid, stem, t0, t1, dur = slots[key]
        if args.prefix and not _paths.matches(stem, args.prefix):
            continue
        mod = _paths.load_scene(p)
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
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\n已写 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
