# -*- coding: utf-8 -*-
"""第六道验收：文字落区（画面里的字只许待在内容安全区里）。

为什么需要它：字幕带（竖屏默认 y 1300–1460）是用户后期自己烧字幕的地方，
画面里任何一个字进去都会被盖住；而标题层又贴着内容区上沿，改个字号就顶出去了。
现有验收里，`check_layout.py` 查图形/卡片越界，`check_text.py` 查"字压字"，
都不查"字出界"。

原理：打开 `motion.TRACK` 后，每次 `c.text()` 都会把（文本, 包围盒）记进
`motion.TEXT_BOXES`；逐场按 fps 采样跑 `frame(t)`，把所有 alpha > 0.05 的文字框
跟允许区比一次。

用法:
    python audit_text_band.py                 # 全部场景
    python audit_text_band.py s03 s07         # 只查指定场次（文件名前缀）
    python audit_text_band.py --fps 2         # 采密一点
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _find_scripts(start: Path) -> Path | None:
    """往上找 <工作区>/管线/scripts（不假定 03-动画 在第几层）。"""
    for base in [start, *start.parents]:
        cand = base / "scripts"
        if (cand / "motion.py").exists():
            return cand
    return None


_sp = _find_scripts(HERE)
if _sp:
    sys.path.insert(0, str(_sp))

import layout as L          # noqa: E402
import motion               # noqa: E402
from motion import TEXT_BOXES  # noqa: E402


def load(name: str):
    """按文件加载场景，避开 scenes 不是包的情况。"""
    p = HERE / "scenes" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, str(p))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="只查这些场次（文件名前缀）")
    ap.add_argument("--fps", type=float, default=1.0, help="采样帧率，默认 1（静置文字够用）")
    ap.add_argument("--top", type=int, default=140)
    ap.add_argument("--bottom", type=int, default=L.SUBTITLE_BAND[0] - 10)
    ap.add_argument("--left", type=int, default=60)
    ap.add_argument("--right", type=int, default=L.W - 60)
    a = ap.parse_args(argv[1:])

    motion.TRACK[0] = True
    bad = 0
    for sid, name, t0, t1, dur in L.SCENE_SLOTS:
        if a.only and not any(name.startswith(k) or sid.lower() == k.lower() for k in a.only):
            continue
        mod = load(name)
        t, worst = 0.0, []
        while t < float(mod.DURATION):
            TEXT_BOXES.clear()
            mod.frame(t)
            for box in TEXT_BOXES:
                if box["a"] <= 0.05 or not box["t"].strip():
                    continue
                x0, y0, x1, y1 = box["box"]
                if y0 < a.top or y1 > a.bottom or x0 < a.left or x1 > a.right:
                    worst.append((round(t, 2), box["t"], [round(v) for v in box["box"]]))
            t += 1.0 / a.fps
        if worst:
            bad += len(worst)
            print(f"[!! ] {sid} {name}: {len(worst)} 处越界")
            for w in worst[:4]:
                print(f"       t={w[0]}s 「{w[1]}」 box={w[2]}")
        else:
            print(f"[OK ] {sid} {name}")

    print(f"\n越界合计 {bad} 处"
          f"（允许区 y {a.top}-{a.bottom} / x {a.left}-{a.right}，"
          f"字幕带 {L.SUBTITLE_BAND[0]}-{L.SUBTITLE_BAND[1]} 不进）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
