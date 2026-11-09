# -*- coding: utf-8 -*-
"""最终合成：人物 + 动画场景 + 画中画过渡，一遍出片。

输入
    03-超分.mp4        1080x1920 的人物母版（已超分）
    scenes/clips/*.mp4 每个场景渲好的 1080x1920 片段
输出
    04-合成.mp4        1080x1920 / 30fps / H.264

为什么不用 ffmpeg 的 overlay 表达式：
    全屏<->缩角的过渡要让人物同时"缩小 + 位移 + 圆角长出来"，
    ffmpeg 里写这种 time 表达式既难读又难改；Python 里每帧算一次反而简单，
    而且场景片段是预先渲好的，这一遍只剩"缩放 + 贴图"，速度够。

用法
    python compose_final.py                    # 全片
    python compose_final.py --from 13 --to 40  # 抽一段试
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import compose
import layout as L
import scene_kit as K

FPS = 30
W, H = L.W, L.H


def round_mask(w: int, h: int, r: int, ss: int = 4) -> Image.Image:
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


_mask_cache: dict[tuple[int, int, int], Image.Image] = {}
_shadow_cache: dict[tuple[int, int, int], Image.Image] = {}


def person_card(person: Image.Image, crop, dest, radius: int, feather: float = 0.0) -> tuple[Image.Image, tuple[int, int]]:
    """从人物整帧里裁一块（crop），贴成 dest 大小的圆角卡片（radius）。

    头像 = crop 头部方块 + dest 220 方块 + radius 110。
    全屏 = crop 整幅 + dest 整幅 + radius 0。
    中间就是"头像慢慢展开、镜头同时拉远"。

    羽化只作用在**蒙版的 alpha** 上：早先版本对整个 card 做高斯模糊，
    结果脸本身也被糊了（220px 的圆里一眼就能看出虚）。
    """
    cx0, cy0, cx1, cy1 = [round(v) for v in crop]
    cx0, cy0 = max(0, cx0), max(0, cy0)
    cx1, cy1 = min(W, cx1), min(H, cy1)
    piece = person.crop((cx0, cy0, cx1, cy1))

    x0, y0, x1, y1 = [round(v) for v in dest]
    w, h = max(2, x1 - x0), max(2, y1 - y0)
    card = piece.resize((w, h), Image.LANCZOS).convert("RGBA")

    # 蒙版缓存带上羽化量，否则 0.7s 过渡里 radius 变、feather 变会取到旧图
    fkey = round(feather, 1)
    key = (w, h, radius, fkey)
    if key not in _mask_cache:
        m = round_mask(w, h, min(radius, min(w, h) // 2))
        if fkey > 0.5:
            m = m.filter(ImageFilter.GaussianBlur(fkey / 3.0))
        _mask_cache[key] = m
    card.putalpha(_mask_cache[key])

    if radius > 6:
        alpha = int(245 * min(1.0, radius / L.PIP_R))
        ImageDraw.Draw(card).rounded_rectangle(
            [1, 1, w - 2, h - 2], radius=max(1, radius - 1),
            outline=(255, 255, 255, alpha), width=L.PIP_BORDER)

        pad = 64
        if key not in _shadow_cache:
            sh = Image.new("L", (w + pad * 2, h + pad * 2), 0)
            ox, oy = L.PIP_SHADOW_OFFSET
            ImageDraw.Draw(sh).rounded_rectangle(
                [pad + ox, pad + oy, pad + w + ox, pad + h + oy],
                radius=radius + 4, fill=L.PIP_SHADOW_ALPHA)
            _shadow_cache[key] = sh.filter(ImageFilter.GaussianBlur(L.PIP_SHADOW))
        out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        out.putalpha(_shadow_cache[key])
        out.alpha_composite(card, (pad, pad))
        return out, (x0 - pad, y0 - pad)

    return card, (x0, y0)


class ClipReader:
    """顺序读取一个场景片段，帧率固定 30fps。"""

    def __init__(self, path: Path):
        self.path = path
        self.proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)
        self.size = W * H * 3
        self.idx = -1

    def read(self) -> Image.Image | None:
        buf = self.proc.stdout.read(self.size)
        if len(buf) < self.size:
            return None
        self.idx += 1
        return Image.frombytes("RGB", (W, H), buf)

    def skip_to(self, frame_idx: int):
        while self.idx < frame_idx - 1:
            if self.read() is None:
                break

    def close(self):
        # 直接 kill：先关 stdout 会让 ffmpeg 写管道失败，刷一屏 Broken pipe
        try:
            self.proc.kill()
            self.proc.stdout.close()
            self.proc.wait(timeout=5)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    base = HERE.parents[0]
    ap.add_argument("--person", default=str(base / "02-剪辑" / "03-超分.mp4"))
    ap.add_argument("--clips", default=str(HERE / "scenes" / "clips"))
    ap.add_argument("--out", default=str(base / "02-剪辑" / "04-合成.mp4"))
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--crf", type=int, default=17)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    # 全片长度以 timemap 的 output_duration 为准（场景只覆盖到 244.85，后面还有 CTA）
    tm = json.loads((base / "02-剪辑" / "timemap.json").read_text(encoding="utf-8"))
    total_dur = float(tm["output_duration"])
    t1 = args.t1 if args.t1 is not None else total_dur
    total = int(round((t1 - args.t0) * FPS))
    start_f = int(round(args.t0 * FPS))

    # 人物解码
    dec = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{args.t0:.3f}",
         "-i", str(args.person), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)

    # 编码
    enc_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-"]
    if not args.no_audio:
        enc_cmd += ["-ss", f"{args.t0:.3f}", "-i", str(args.person), "-map", "0:v:0",
                    "-map", "1:a:0", "-c:a", "copy", "-shortest"]
    enc_cmd += ["-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.out)]
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)

    bg_static = K.background(2).reduce(2).convert("RGB")

    clip: ClipReader | None = None
    clip_start = -1.0
    written = 0
    import time
    t_start = time.time()

    for n in range(total):
        t = args.t0 + n / FPS
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        person = Image.frombytes("RGB", (W, H), buf)

        slot = None
        for sid, name, a, b, dur in L.SCENE_SLOTS:
            if a - 1e-6 <= t < b - 1e-6:
                slot = (sid, name, a, b, dur)
                break

        state, prog = L.state_at(t)

        if state == "full":
            frame = person
            if clip:
                clip.close()
                clip = None
        else:
            if slot:
                path = Path(args.clips) / f"{slot[1]}.mp4"
                if clip is None or clip.path != path:
                    if clip:
                        clip.close()
                    clip = ClipReader(path)
                    clip_start = slot[2]
                    target = int(round((t - slot[2]) * FPS))
                    clip.skip_to(target)
                scene = clip.read()
                if scene is None:
                    scene = bg_static.copy()
            else:
                scene = bg_static.copy()

            # pip_params 的 progress：0=全屏人物，1=圆头像。
            # state_at 给的 prog 是"这段过渡已经走了多少"，所以 to_full 要取 1-prog，
            # 否则回到全屏的路上会先缩成圆、最后一帧硬跳（2026-11-04 修）。
            if state == "pip":
                p = 1.0
            elif state == "to_full":
                p = 1.0 - prog
            else:
                p = prog
            crop, dest, radius, feather = L.pip_params(p)
            layer, (lx, ly) = person_card(person, crop, dest, radius, feather)
            frame = scene.convert("RGBA")
            frame.alpha_composite(layer, (lx, ly))
            frame = frame.convert("RGB")

        enc.stdin.write(frame.tobytes())
        written += 1
        if written % 150 == 0:
            el = time.time() - t_start
            print(f"  {written}/{total}  {el:.0f}s  eta {el / written * (total - written):.0f}s", flush=True)

    enc.stdin.close()
    enc.wait()
    if clip:
        clip.close()
    dec.kill()
    dec.stdout.close()
    dec.wait()
    print(f"[done] {args.out}  {written} 帧  {(time.time() - t_start):.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
