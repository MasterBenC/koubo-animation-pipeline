#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""场景渲染器：驱动一个 scene 模块，把帧直接打进 ffmpeg（不落盘、不开管道给浏览器）。

scene 模块约定:
    DURATION = 6.5                      # 秒
    W, H = 1080, 1920                   # 可选，默认 1080x1920
    def frame(t: float) -> Image.Image  # RGBA，秒

用法:
    python render_scene.py scenes/s01.py -o out/s01.webm --alpha
    python render_scene.py scenes/s01.py -o out/s01.mp4                # 不透明背景
    python render_scene.py scenes/s01.py --still 2.4 -o out/s01.png    # 单帧
    python render_scene.py scenes/s01.py -o out/s01.mp4 --contact 12   # 联系表
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image


def load_scene(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def ffmpeg_cmd(out: Path, w: int, h: int, fps: int, alpha: bool, crf: int, preset: str):
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if out.suffix.lower() in (".png",):
        raise ValueError("png is not a video target")
    if alpha or out.suffix.lower() == ".webm":
        tail = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p" if alpha else "yuv420p",
                "-b:v", "0", "-crf", str(crf), "-row-mt", "1", "-cpu-used", "4",
                "-auto-alt-ref", "0", str(out)]
    else:
        tail = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
                "-preset", preset, "-movflags", "+faststart", str(out)]
    return base + tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--alpha", action="store_true")
    ap.add_argument("--crf", type=int, default=26)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--still", type=float, default=None)
    ap.add_argument("--stills", default=None, help="逗号分隔的多个时间点，出拼图")
    ap.add_argument("--from", dest="t_from", type=float, default=0.0)
    ap.add_argument("--to", dest="t_to", type=float, default=None)
    ap.add_argument("--contact", type=int, default=0, help="出 N 帧联系表 PNG")
    args = ap.parse_args()

    scene_path = Path(args.scene).resolve()
    mod = load_scene(scene_path)
    W = getattr(mod, "W", 1080)
    H = getattr(mod, "H", 1920)
    dur = float(getattr(mod, "DURATION"))
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.still is not None:
        img = mod.frame(args.still)
        img.save(out)
        print(f"[still] t={args.still} -> {out} ({img.size[0]}x{img.size[1]})")
        return 0

    if args.stills:
        ts = [float(x) for x in args.stills.split(",") if x.strip()]
        imgs = [mod.frame(t) for t in ts]
        cols = min(len(imgs), 4)
        rows = (len(imgs) + cols - 1) // cols
        tw, th = W // 3, H // 3
        sheet = Image.new("RGB", (cols * tw, rows * th), (18, 18, 18))
        for i, im in enumerate(imgs):
            thumb = im.convert("RGB").resize((tw - 4, th - 4), Image.LANCZOS)
            sheet.paste(thumb, ((i % cols) * tw + 2, (i // cols) * th + 2))
        sheet.save(out)
        print(f"[stills] {len(imgs)} 帧 -> {out}")
        return 0

    t_to = args.t_to if args.t_to is not None else dur
    n = int(round((t_to - args.t_from) * args.fps))
    if args.contact:
        fps_out = args.contact / max(1e-6, (t_to - args.t_from))
    else:
        fps_out = args.fps

    if args.contact:
        idx = [int(round(i * (n - 1) / max(1, args.contact - 1))) for i in range(args.contact)]
        ts = [args.t_from + i / fps_out for i in idx]
        imgs = [mod.frame(t) for t in ts]
        cols = 4 if args.contact >= 4 else args.contact
        rows = (len(imgs) + cols - 1) // cols
        tw, th = W // 3, H // 3
        sheet = Image.new("RGB", (cols * tw, rows * th), (18, 18, 18))
        for i, im in enumerate(imgs):
            thumb = im.convert("RGB").resize((tw - 4, th - 4), Image.LANCZOS)
            sheet.paste(thumb, ((i % cols) * tw + 2, (i // cols) * th + 2))
        out = out.with_suffix(".png")
        sheet.save(out)
        print(f"[contact] {len(imgs)} 帧 -> {out}")
        return 0

    cmd = ffmpeg_cmd(out, W, H, args.fps, args.alpha, args.crf, args.preset)
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = args.t_from + i / args.fps
            img = mod.frame(t)
            if img.size != (W, H):
                img = img.resize((W, H), Image.LANCZOS)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            proc.stdin.write(img.tobytes())
            if i % 90 == 0:
                el = time.time() - t0
                print(f"  {i}/{n}  {el:.1f}s  eta {el/(i+1)*(n-i-1):.0f}s", flush=True)
        proc.stdin.close()
        rc = proc.wait()
    except Exception:
        proc.kill()
        raise
    if rc != 0:
        raise SystemExit(f"ffmpeg failed rc={rc}")
    el = time.time() - t0
    size = out.stat().st_size / 1e6
    print(f"[done] {out.name} {n} 帧 {el:.1f}s ({n/el:.1f} fps) {size:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
