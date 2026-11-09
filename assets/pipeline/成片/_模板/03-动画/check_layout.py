# -*- coding: utf-8 -*-
"""版式体检：用像素证明"画中画没压到内容"，不靠肉眼也不靠视觉模型。

做法：逐帧渲染场景 -> 与"只有背景"的同一帧做差 -> 得到真正有内容的像素
-> 检查这些像素有没有落进画中画矩形 / 安全区外。

用法:
    python check_layout.py scenes/s01_valuation_haircut.py
    python check_layout.py scenes/*.py --step 0.5
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import layout as L


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bg_frame():
    import scene_kit as K
    c = K.canvas(0.0)
    return np.asarray(c.finish().convert("RGB")).astype(np.int16)


def diff_mask(img: Image.Image, bg: np.ndarray, thr: int = 10) -> np.ndarray:
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    return (np.abs(a - bg).max(axis=2) > thr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="+")
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--margin", type=int, default=6, help="画中画外扩余量")
    ap.add_argument("--save", action="store_true", help="把违规帧存下来")
    args = ap.parse_args()

    bg = bg_frame()
    # 画中画 = 圆（含外扩余量），不是矩形
    yy, xx = np.mgrid[0:L.H, 0:L.W]
    pip = ((xx - L.PIP_CX) ** 2 + (yy - L.PIP_CY) ** 2) <= (L.PIP_R + args.margin) ** 2

    # 安全区外
    s = L.SAFE
    safe = np.zeros(bg.shape[:2], dtype=bool)
    safe[s["top"]:L.H - s["bottom"], s["left"]:L.W - s["right"]] = True

    # 字幕带：用户后期烧，内容一层都不许进
    band = np.zeros(bg.shape[:2], dtype=bool)
    b0, b1 = L.SUBTITLE_BAND
    band[b0:b1, :] = True

    bad_total = 0
    for sp in args.scenes:
        path = Path(sp)
        mod = load(path)
        dur = float(getattr(mod, "DURATION", 10.0))
        ts = [round(i * args.step, 2) for i in range(int(dur / args.step) + 1)]
        worst = 0.0
        worst_t = 0.0
        outside_px = 0
        band_px = 0
        band_worst = 0
        band_t = 0.0
        pip_frames = []
        for t in ts:
            img = mod.frame(min(t, dur - 0.01))
            m = diff_mask(img, bg)
            in_pip = int((m & pip).sum())
            if in_pip > worst:
                worst, worst_t = in_pip, t
            if in_pip:
                pip_frames.append((t, in_pip))
            nb = int((m & band).sum())
            if nb > band_worst:
                band_worst, band_t = nb, t
            band_px += nb
            outside_px += int((m & ~safe).sum())
            if args.save and (in_pip or nb):
                out = HERE / "preview" / "violations"
                out.mkdir(parents=True, exist_ok=True)
                img.convert("RGB").save(out / f"{path.stem}-t{t:.2f}-{in_pip}px.png")

        status = "OK " if worst == 0 and band_worst < 300 else "FAIL"
        bad_total += 0 if status.startswith("OK") else 1
        safe_note = "" if outside_px < 500 else "  <- 有元素越出安全区（坠落/飞出镜头的可以接受，静止内容不行）"
        band_note = "" if band_worst < 300 else f"  <- 进了字幕带 峰值{band_worst}px @t={band_t:.2f}"
        print(f"[{status}] {path.name:34} frames={len(ts):3d}  "
              f"圆侵入={int(worst):6d}px @t={worst_t:5.2f}  "
              f"字幕带={band_worst:5d}px  安全区外={outside_px}{safe_note}{band_note}")
        if pip_frames:
            head = ", ".join(f"t{t:.2f}:{n}px" for t, n in pip_frames[:6])
            print(f"       圆违规时段: {head}{' ...' if len(pip_frames) > 6 else ''}")
    return 0 if bad_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
