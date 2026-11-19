# -*- coding: utf-8 -*-
"""版式体检：用像素证明「内容没压到圆头像、没进字幕带、没出安全区」，不靠肉眼。

做法：逐帧渲染场景 -> 与「只有背景」的同一帧做差 -> 得到真正有内容的像素
-> 检查这些像素有没有落进圆头像（圆形距离掩码，不是矩形包围盒）/ 字幕带 / 安全区外。

用法:
    python check_layout.py scenes/s01_valuation_haircut.py
    python check_layout.py s01 s07 --step 0.5
    python check_layout.py s01 --save          # 把违规帧存进 preview/violations/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import _paths

_paths.ensure_import_path()

import layout as L  # noqa: E402


def bg_frame():
    import scene_kit as K
    return np.asarray(K.canvas(0.0).finish().convert("RGB")).astype(np.int16)


def scene_bg(mod, t: float):
    """场景自带 `bg_frame(t)` 时，用它渲「同一帧的纯背景」做差。

    这是照片底 / 双色底 / 点阵底唯一正确的基准：通用底（`K.canvas`）和场景真实背景
    差了整张图，直接拿通用底做差会把每一帧都判成「满屏内容」——19 场能全假失败一遍。
    场景没写 `bg_frame` 就返回 None，退回通用底。
    """
    fn = getattr(mod, "bg_frame", None)
    if fn is None:
        return None
    return np.asarray(fn(t).finish().convert("RGB")).astype(np.int16)


def drop_scrim(mask: np.ndarray) -> np.ndarray:
    """把顶部固定薄膜（K.scrim_box）从「内容」里排除——它是背景件，不是这一场画的。"""
    import scene_kit as K
    x0, y0, x1, y1 = K.scrim_box()
    mask[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = False
    return mask


def diff_mask(img: Image.Image, bg: np.ndarray, thr: int = 10) -> np.ndarray:
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    return (np.abs(a - bg).max(axis=2) > thr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="+", help="场景路径或 sNN（大小写不敏感）")
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--margin", type=int, default=6, help="圆头像外扩余量")
    ap.add_argument("--save", action="store_true", help="把违规帧存下来")
    args = ap.parse_args()

    paths = []
    for arg in args.scenes:
        try:
            paths.append(_paths.resolve_scene(arg))
        except FileNotFoundError as exc:
            print(f"[!] {exc}")
            return 2

    bg = bg_frame()
    # 圆头像 = 圆（含外扩余量），不是矩形。互切模式没有圆头像，这一项直接跳过。
    yy, xx = np.mgrid[0:L.H, 0:L.W]
    if L.MODE == "corner" and L.PIP_R > 0:
        pip = ((xx - L.PIP_CX) ** 2 + (yy - L.PIP_CY) ** 2) <= (L.PIP_R + args.margin) ** 2
    else:
        pip = np.zeros((L.H, L.W), dtype=bool)
        print(f"[注] 当前模式 {L.ACTIVE_PROFILE} 没有画中画，跳过圆侵入检查")

    # 安全区外
    s = L.SAFE
    safe = np.zeros(bg.shape[:2], dtype=bool)
    safe[s["top"]:L.H - s["bottom"], s["left"]:L.W - s["right"]] = True

    # 字幕带：用户后期烧，动画一层都不许进（图形也算）
    band = np.zeros(bg.shape[:2], dtype=bool)
    b0, b1 = L.SUBTITLE_BAND
    band[b0:b1, :] = True

    bad_total = 0
    for path in paths:
        mod = _paths.load_scene(path)
        dur = _paths.duration(mod)
        ts = [round(i * args.step, 2) for i in range(int(dur / args.step) + 1)]
        worst = 0.0
        worst_t = 0.0
        outside_px = 0
        band_worst = 0
        band_t = 0.0
        pip_frames = []
        no_bg = []
        for t in ts:
            tt = min(t, dur - 0.01)
            img = mod.frame(tt)
            ref = scene_bg(mod, tt)
            if ref is None:
                ref = bg
            m = drop_scrim(diff_mask(img, ref))
            if ref is bg and m.mean() > 0.25:
                no_bg.append(t)
            in_pip = int((m & pip).sum())
            if in_pip > worst:
                worst, worst_t = in_pip, t
            if in_pip:
                pip_frames.append((t, in_pip))
            nb = int((m & band).sum())
            if nb > band_worst:
                band_worst, band_t = nb, t
            outside_px += int((m & ~safe).sum())
            if args.save and (in_pip or nb):
                out = _paths.HERE / "preview" / "violations"
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
        if no_bg:
            print(f"       [!] 本场缺模块级 def bg_frame(t)（{len(no_bg)}/{len(ts)} 帧与通用底差 >25%），"
                  f"圆/字幕带的数字可能全是背景差、不是内容越界；"
                  f"把 frame() 里的背景调用提成 bg_frame(t) 再跑。")
    return 0 if bad_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
