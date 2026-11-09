#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""纯 Python（PIL）动画引擎：不依赖浏览器、不依赖命名管道，沙箱内可跑。

设计约束
  1. 所有坐标用「成片像素」写，内部按 SS 倍超采样绘制再缩回，曲线/文字边缘干净。
  2. 一切由 t 决定，同 t 必出同一帧（确定性），可任意跳帧重渲。
  3. 只暴露绘制原语，不隐藏动效：时间曲线由场景自己算，避免"库替你决定节奏"。

用法
    from motion import Canvas, ease, lerp, C
    c = Canvas(1080, 1920)
    c.rounded_rect((80, 300, 1000, 900), 40, fill=C.bg_card)
    c.text(140, 380, "807", font="bahn", size=200, fill=C.amber)
    img = c.finish()          # -> RGBA Image
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FONTS = {
    "yh": "msyh.ttc",          # 微软雅黑
    "yh_b": "msyhbd.ttc",      # 微软雅黑 Bold
    "yh_l": "msyhl.ttc",
    "bahn": "bahnschrift.ttf",  # DIN 风格，数字好看
    "consola": "consola.ttf",
    "consolab": "consolab.ttf",
    "deng": "Deng.ttf",
    "deng_b": "Dengb.ttf",
    "noto": "NotoSansSC-VF.ttf",
    "noto_b": "NotoSansSC-VF.ttf",
}

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_WARNED_MIXED = [False]   # 字体回退只提示一次，别每帧刷屏

# 排字检查：打开 TRACK 后，每次画字都会把（文本, 包围盒）记进 TEXT_BOXES。
# 用来逐帧算"有没有两个字压在一起"，比肉眼看缩略图靠谱。
TRACK = [False]
TEXT_BOXES: list = []

# 非 ASCII 一律用中文字体：纯西文字体（Bahnschrift 等）没有 ≈ → ★ × 这些符号，
# 用它们画会出方框。汉字网格里的字符覆盖率最高，直接按"非 ASCII 归中文"切分最省事。
_CJK_RE = re.compile(r"[^\x00-\x7F]")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key in _font_cache:
        return _font_cache[key]
    path = FONT_DIR / FONTS.get(name, name)
    f = ImageFont.truetype(str(path), size)
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------- 颜色
@dataclass(frozen=True)
class Palette:
    bg: tuple = (14, 20, 32, 255)          # #0E1420
    bg_deep: tuple = (8, 11, 18, 255)
    card: tuple = (22, 32, 46, 235)        # #16202E
    card_solid: tuple = (22, 32, 46, 255)
    line: tuple = (127, 166, 201, 90)      # #7FA6C9
    line_soft: tuple = (127, 166, 201, 40)
    text: tuple = (242, 240, 234, 255)     # #F2F0EA
    text_dim: tuple = (159, 179, 200, 255)  # #9FB3C8
    amber: tuple = (242, 179, 75, 255)     # #F2B34B
    danger: tuple = (255, 122, 47, 255)    # #FF7A2F
    cold: tuple = (79, 209, 197, 255)      # #4FD1C5
    red: tuple = (226, 64, 47, 255)        # #E2402F
    white: tuple = (255, 255, 255, 255)
    black: tuple = (0, 0, 0, 255)


C = Palette()


# ---------------------------------------------------------------- 缓动
def clamp(x, a=0.0, b=1.0):
    return a if x < a else (b if x > b else x)


def lerp(a, b, p):
    return a + (b - a) * p


def ease_out_cubic(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_in_cubic(p):
    p = clamp(p)
    return p ** 3


def ease_in_out_cubic(p):
    p = clamp(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_out_expo(p):
    p = clamp(p)
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def ease_out_back(p, s=1.7):
    p = clamp(p)
    return 1 + (s + 1) * (p - 1) ** 3 + s * (p - 1) ** 2


def spring(p, freq=3.0, damp=6.0):
    """0->1 的带过冲弹性，p 为 0..1 的归一化时间。"""
    p = clamp(p)
    if p >= 1:
        return 1.0
    return 1 - math.exp(-damp * p) * math.cos(freq * 2 * math.pi * p)


def stage(t, start, dur, fn=ease_out_cubic):
    """把绝对时间切成 0..1 的局部进度。"""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return fn(clamp((t - start) / dur))


def alpha_in(t, start, dur=0.35):
    return ease_out_cubic(clamp((t - start) / dur))


# ---------------------------------------------------------------- 画布
class Canvas:
    def __init__(self, w=1080, h=1920, ss=2, bg=None, base: Image.Image | None = None):
        self.w, self.h, self.ss = w, h, ss
        if base is not None:
            # 关键：底图不透明时画布用 RGB。
            # Pillow 的 ImageDraw 只有在 **RGB 画布 + RGBA 画笔** 时才真正做 alpha 混合；
            # 在 RGBA 画布上是"直接写 RGB、顺手改 alpha"，压平成 RGB 后透明度被丢掉，
            # 结果就是：淡入变成硬切、空进度条看起来是满的、半透明色块变实色。
            self.img = base.convert("RGB") if base.mode == "RGBA" else base.copy()
        else:
            self.img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        if bg is not None and base is None:
            self.draw.rectangle([0, 0, w * ss, h * ss], fill=bg)

    # ---- 基础
    def _s(self, v):
        return int(round(v * self.ss))

    def _box(self, box):
        x0, y0, x1, y1 = box
        return [self._s(x0), self._s(y0), self._s(x1), self._s(y1)]

    def rect(self, box, fill=None, outline=None, width=1, opacity=1.0):
        if opacity <= 0.01:
            return
        self.draw.rectangle(self._box(box), fill=_with_alpha(fill, opacity),
                            outline=_with_alpha(outline, opacity),
                            width=max(1, self._s(width)))

    def rounded_rect(self, box, r, fill=None, outline=None, width=1, corners=None,
                     opacity=1.0):
        if opacity <= 0.01:
            return
        self.draw.rounded_rectangle(self._box(box), radius=self._s(r),
                                    fill=_with_alpha(fill, opacity),
                                    outline=_with_alpha(outline, opacity),
                                    width=max(1, self._s(width)), corners=corners)

    def ellipse(self, box, fill=None, outline=None, width=1, opacity=1.0):
        if opacity <= 0.01:
            return
        self.draw.ellipse(self._box(box), fill=_with_alpha(fill, opacity),
                          outline=_with_alpha(outline, opacity),
                          width=max(1, self._s(width)))

    def polygon(self, pts, fill=None, outline=None, width=1, opacity=1.0):
        if opacity <= 0.01:
            return
        p = [(self._s(x), self._s(y)) for x, y in pts]
        self.draw.polygon(p, fill=_with_alpha(fill, opacity))
        if outline:
            self.draw.line(p + [p[0]], fill=_with_alpha(outline, opacity),
                           width=max(1, self._s(width)), joint="curve")

    def line(self, pts, fill, width=2, joint="curve", opacity=1.0):
        if opacity <= 0.01:
            return
        p = [(self._s(x), self._s(y)) for x, y in pts]
        self.draw.line(p, fill=_with_alpha(fill, opacity),
                       width=max(1, self._s(width)), joint=joint)

    # ---- 文字
    def text(self, x, y, s, font_name="yh", size=64, fill=C.text, anchor="la",
             tracking=0, shadow=None, shadow_blur=0, shadow_offset=(0, 8),
             stroke=0, stroke_fill=None, opacity=1.0):
        f = font(font_name, self._s(size))
        if opacity <= 0.01 or not s:
            return (0, 0)
        if font_name in ("bahn", "consola", "consolab") and _CJK_RE.search(s):
            # 纯西文字体画中文会出方框（tofu）。自动回退到中文字体，并亮一次红灯。
            if not _WARNED_MIXED[0]:
                print(f"[motion] WARN 字体 {font_name} 不含中文，已自动回退 yh_b：{s[:20]!r}")
                _WARNED_MIXED[0] = True
            font_name = "yh_b"
            f = font(font_name, self._s(size))
        col = fill if opacity >= 0.99 else _with_alpha(fill, opacity)
        if tracking == 0:
            self.draw.text((self._s(x), self._s(y)), s, font=f, fill=col,
                           anchor=anchor, stroke_width=self._s(stroke),
                           stroke_fill=stroke_fill)
            if TRACK[0]:
                bb = self.draw.textbbox((self._s(x), self._s(y)), s, font=f, anchor=anchor)
                TEXT_BOXES.append({"t": s, "box": [bb[0] / self.ss, bb[1] / self.ss,
                                                  bb[2] / self.ss, bb[3] / self.ss],
                                   "size": size, "a": opacity})
            return _text_size(f, s, self.ss)

        # 逐字排，支持字距；anchor 只支持左对齐系列
        cx = x
        total_w = 0
        widths = [_text_size(f, ch, self.ss)[0] for ch in s]
        total_w = sum(widths) + tracking * (len(s) - 1)
        if anchor.startswith("m"):
            cx = x - total_w / 2
        elif anchor.startswith("r"):
            cx = x - total_w
        first_x = cx
        for ch, w in zip(s, widths):
            self.draw.text((self._s(cx), self._s(y)), ch, font=f, fill=col, anchor="l" + anchor[1:],
                           stroke_width=self._s(stroke), stroke_fill=stroke_fill)
            cx += w + tracking
        if TRACK[0]:
            TEXT_BOXES.append({"t": s, "box": [first_x, y, first_x + total_w, y + size],
                               "size": size, "a": opacity})
        return (total_w, size)

    def text_mixed(self, x, y, s, size=44, fill=C.text, ascii_font="bahn", cjk_font="yh_b",
                   tracking=0, opacity=1.0, ascii_scale=1.0, cjk_scale=1.0):
        """中西混排：数字/西文用 ascii_font，汉字自动切到 cjk_font。

        y 是**基线**（不是顶边），因为两种字体的 ascent 不同，按基线对齐才不会跳。
        返回这段文字的宽度，方便接着往右画。
        """
        if opacity <= 0.01 or not s:
            return 0.0
        col = fill if opacity >= 0.99 else _with_alpha(fill, opacity)
        runs, buf, buf_cjk = [], "", None
        for ch in s:
            is_cjk = bool(_CJK_RE.match(ch))
            if buf and is_cjk != buf_cjk:
                runs.append((buf, buf_cjk))
                buf = ""
            buf += ch
            buf_cjk = is_cjk
        if buf:
            runs.append((buf, buf_cjk))

        cx = x
        for text, is_cjk in runs:
            fname = cjk_font if is_cjk else ascii_font
            fs = size * (cjk_scale if is_cjk else ascii_scale)
            f = font(fname, self._s(fs))
            self.draw.text((self._s(cx), self._s(y)), text, font=f, fill=col, anchor="ls")
            w = self.draw.textlength(text, font=f) / self.ss
            cx += w + tracking * (len(text) if tracking else 0)
        if TRACK[0]:
            TEXT_BOXES.append({"t": s, "box": [x, y - size * 0.82, cx, y + size * 0.22],
                               "size": size, "a": opacity})
        return cx - x

    def text_shadow(self, x, y, s, font_name, size, fill, anchor="la", tracking=0,
                    blur=24, offset=(0, 14), shadow_alpha=170):
        """先画一层模糊阴影，再画字。"""
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = font(font_name, self._s(size))
        d.text((self._s(x + offset[0]), self._s(y + offset[1])), s, font=f,
               fill=(0, 0, 0, shadow_alpha), anchor=anchor)
        layer = layer.filter(ImageFilter.GaussianBlur(self._s(blur) / 2))
        self._comp(layer)
        self.text(x, y, s, font_name, size, fill, anchor, tracking)

    # ---- 组合
    def _comp(self, layer, pos=(0, 0)):
        """把一张 RGBA 图层叠到画布上（RGB / RGBA 画布都支持，只贴有内容的区域）。"""
        if self.img.mode != "RGB":
            self.img.alpha_composite(layer, pos)
            return
        bb = layer.getbbox()
        if not bb:
            return
        ox, oy = pos
        x0, y0, x1, y1 = bb[0] + ox, bb[1] + oy, bb[2] + ox, bb[3] + oy
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.img.width, x1), min(self.img.height, y1)
        if x1 <= x0 or y1 <= y0:
            return
        sub = self.img.crop((x0, y0, x1, y1)).convert("RGBA")
        sub.alpha_composite(layer.crop((x0 - ox, y0 - oy, x1 - ox, y1 - oy)))
        self.img.paste(sub.convert("RGB"), (x0, y0))

    def layer(self):
        """新建一个同尺寸透明层，返回 (layer_img, draw)。"""
        im = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        return im, ImageDraw.Draw(im, "RGBA")

    def composite(self, im, opacity=1.0):
        if opacity <= 0.01:
            return
        if opacity < 0.99:
            a = im.getchannel("A").point(lambda v: int(v * opacity))
            im = im.copy()
            im.putalpha(a)
        self._comp(im)

    def paste(self, im, x, y, opacity=1.0):
        if opacity <= 0.01:
            return
        if opacity < 0.99:
            a = im.getchannel("A").point(lambda v: int(v * opacity))
            im = im.copy()
            im.putalpha(a)
        self._comp(im, (self._s(x), self._s(y)))

    def glow(self, box, color, radius=40, strength=200, rounded=40):
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer, "RGBA")
        d.rounded_rectangle(self._box(box), radius=self._s(rounded),
                            fill=_with_alpha(color, strength / 255))
        layer = layer.filter(ImageFilter.GaussianBlur(self._s(radius) / 2))
        self._comp(layer)

    def vignette(self, strength=90):
        """边缘压暗，让注意力回到中心。"""
        mask = Image.new("L", (self.w * self.ss, self.h * self.ss), 0)
        d = ImageDraw.Draw(mask)
        w, h = mask.size
        d.ellipse([-w * 0.25, -h * 0.15, w * 1.25, h * 1.15], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(self._s(160)))
        dark = Image.new("RGBA", mask.size, (0, 0, 0, strength))
        if self.img.mode == "RGB":
            rgba = self.img.convert("RGBA")
            rgba.alpha_composite(dark)
            self.img = Image.composite(rgba.convert("RGB"), self.img, mask)
        else:
            self.img = Image.composite(self.img, Image.alpha_composite(self.img, dark), mask)
        self.draw = ImageDraw.Draw(self.img, "RGBA")

    def finish(self) -> Image.Image:
        if self.ss == 1:
            return self.img
        # 整数倍超采样用 reduce(2)：box 平均，边缘同样干净，但比 LANCZOS 快 5 倍
        # （2160x3840 -> 1080x1920：141ms vs 28ms，逐帧渲染时这是最大的一笔）
        if float(self.ss).is_integer():
            return self.img.reduce(int(self.ss))
        return self.img.resize((self.w, self.h), Image.LANCZOS)


def _with_alpha(color, a):
    if color is None:
        return None
    if len(color) == 4:
        return (color[0], color[1], color[2], int(color[3] * a))
    return (color[0], color[1], color[2], int(255 * a))


def _text_size(f: ImageFont.FreeTypeFont, s: str, ss: int = 1):
    try:
        b = f.getbbox(s)
        return ((b[2] - b[0]) / ss, (b[3] - b[1]) / ss)
    except Exception:
        return (f.getlength(s) / ss, f.size / ss)


# ---------------------------------------------------------------- 渐变/工具
def vertical_gradient(w, h, top, bottom):
    base = Image.new("RGBA", (1, h))
    px = base.load()
    for y in range(h):
        p = y / max(1, h - 1)
        px[0, y] = (
            int(lerp(top[0], bottom[0], p)),
            int(lerp(top[1], bottom[1], p)),
            int(lerp(top[2], bottom[2], p)),
            int(lerp(top[3] if len(top) > 3 else 255, bottom[3] if len(bottom) > 3 else 255, p)),
        )
    return base.resize((w, h), Image.BILINEAR)


def human_num(v: float, digits: int = 0) -> str:
    if digits:
        return f"{v:,.{digits}f}"
    return f"{round(v):,}"


def fmt_yi(v_yi: float) -> str:
    """亿 单位数字，整数不带小数。"""
    if abs(v_yi) >= 100:
        return f"{v_yi:,.0f}"
    if abs(v_yi) >= 10:
        return f"{v_yi:,.1f}".rstrip("0").rstrip(".")
    return f"{v_yi:,.2f}".rstrip("0").rstrip(".")
