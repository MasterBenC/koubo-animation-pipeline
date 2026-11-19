# -*- coding: utf-8 -*-
"""场景工具箱：把"视觉语法"固定下来，每个场景只写自己的内容。

所有场景共用同一套：底色、网格、光、章节角标、标题层级、数字滚动、分隔线、条形、箭头、标签。
这样 16 个场景看起来是一条片子，而不是 16 个人做的 PPT。

坐标纪律（与 layout.py 一致）：
    所有落点从 layout 的常量推：X = L.CONTENT[0]（左沿）、CONTENT_TOP/BOTTOM、
    SAFE["top"]。圆头像 / 字幕带的位置也在 layout 里，场景里一律不写死像素。
    标题层只用 `scene_head()`，它保证字落在 layout.TITLE_BAND 内。

画面里的字（2026-11 定稿）：每场一行标题 + 可选一句副标，回答"这场在讲什么"。
    文案集中在下面这个 `TEXT` 字典里，一行一场；改字只改这里，重跑场景即可。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import _paths

_paths.ensure_import_path()

from PIL import Image, ImageDraw

import layout as L
from motion import (C, Canvas, clamp, ease_in_out_cubic, ease_out_back, ease_out_cubic,
                    lerp, stage, vertical_gradient)

W, H = L.W, L.H
X = L.CONTENT[0]          # 内容左沿（默认 72）
XN = L.W // 2             # 左栏右界（默认 540）

# ---------------------------------------------------------------- 标题层文案
# 一行一场：键 = 场景文件主干，值 = 标题 或 (标题, 副标)。
# 副标可省；标题不复述台词，只回答"这场在讲什么"；数字口径要和画面、字幕一致。
TEXT: dict[str, object] = {
    # "s01_valuation_haircut": ("估值被砍掉三分之一", "两万亿的预期，一夜回到一万五"),
}

# 标题层开关：mid（标题+副标，默认）/ light（只标题）/ off（纯图，给用户看两版用）
TITLE_MODE = os.environ.get("KOUBO_TITLE", "mid").strip().lower()


def title_for(key: str) -> tuple[str, str]:
    """取某场的 (标题, 副标)；没配就是两个空串。"""
    hit = TEXT.get(key)
    if not hit:
        return ("", "")
    if isinstance(hit, str):
        return (hit, "")
    title = str(hit[0]) if hit else ""
    sub = str(hit[1]) if len(hit) > 1 and hit[1] else ""
    return (title, sub)

# ---------------------------------------------------------------- 底层

_bg_cache: dict[int, Image.Image] = {}


def background(ss: int = 2) -> Image.Image:
    """渐变底 + 网格 + 左上冷光，只算一次。"""
    if ss in _bg_cache:
        return _bg_cache[ss]
    c = Canvas(W, H, ss=ss)
    grad = vertical_gradient(W * ss, H * ss, (10, 16, 24, 255), (20, 30, 44, 255))
    c.img.alpha_composite(grad)
    for x in range(0, W + 108, 108):
        c.line([(x, 0), (x, H)], (127, 166, 201, 14), width=1)
    for y in range(0, H, 108):
        c.line([(0, y), (W, y)], (127, 166, 201, 10), width=1)
    c.glow((-240, -300, 660, 260), (79, 209, 197, 255), radius=180, strength=24, rounded=300)
    _bg_cache[ss] = c.img
    return c.img


def canvas(t: float = 0.0, ss: int = 2) -> Canvas:
    return Canvas(W, H, ss=ss, base=background(ss))


# ---------------------------------------------------------------- 文字

def chapter(c: Canvas, t: float, idx: str, label: str, y: float | None = None,
            t_in: float = 0.10):
    """左上角章节角标：一条琥珀竖条 + 编号 + 名称。

    与 `scene_head()` **二选一**：章节标是"第几章"的导航，标题层是"这场讲什么"。
    两个都上会在同一条带里打架（这也是当年"字太多"的来源）。
    """
    y = L.TITLE_BAND[0] if y is None else y
    a = stage(t, t_in, 0.45)
    if a <= 0:
        return
    c.rect((X, y + 6, X + 7, y + 46), fill=C.amber, opacity=a)
    c.text(X + 22, y - 4, idx, "bahn", 38, C.amber, opacity=a, tracking=2)
    c.text(X + 90, y - 4, label, "yh", 38, C.text_dim, opacity=a, tracking=3)


def headline(c: Canvas, t: float, text: str, y: float | None = None, size: int = 60,
             t_in: float = 0.20, dur: float = 0.55, color=None):
    """内容区大标题（不是标题层）。y 默认落在内容区上沿内侧。"""
    y = L.CONTENT[1] + 40 if y is None else y
    a = stage(t, t_in, dur)
    if a <= 0:
        return
    # 轻微上浮入场
    dy = (1 - ease_out_cubic(a)) * 18
    c.text(X, y + dy, text, "yh_b", size, color or C.text, opacity=a)


def label(c: Canvas, t: float, text: str, y: float, size: int = 34, color=None,
          t_in: float = 0.0, x: float = X, tracking: int = 2, alpha: float = 1.0):
    a = stage(t, t_in, 0.40) * alpha
    if a <= 0:
        return
    c.text(x, y, text, "yh", size, color or C.text_dim, opacity=a, tracking=tracking)


def number(c: Canvas, t: float, value: float, x: float, y: float, size: int,
           color=None, decimals: int = 0, t_in: float = 0.6, dur: float = 1.30,
           bounce: float = 1.35, prefix: str = "", suffix: str = "") -> float:
    """滚动数字，带回弹。返回最终宽度。"""
    a = clamp((t - t_in) / 0.30)
    if a <= 0.01:
        return 0.0
    p = clamp((t - t_in) / dur)
    v = value * ease_out_cubic(p)
    pop = ease_out_back(clamp((t - t_in) / (dur * 0.62)), bounce)
    s = int(size * (0.90 + 0.10 * pop))
    text = prefix + (f"{v:,.{decimals}f}") + suffix
    c.text(x, y, text, "bahn", s, color or C.amber, opacity=a)
    return len(text) * s * 0.56


def rule(c: Canvas, t: float, y: float, x0: float = X, x1: float = XN,
         t_in: float = 0.0, dur: float = 0.55, color=(127, 166, 201, 80), width: int = 2):
    d = stage(t, t_in, dur, ease_in_out_cubic)
    if d <= 0:
        return
    c.line([(x0, y), (x0 + (x1 - x0) * d, y)], color, width=width)


# ---------------------------------------------------------------- 标题层（唯一允许的画字入口）
_SCRIM_CACHE: dict[int, Image.Image] = {}


def scrim_box() -> tuple[int, int, int, int]:
    """顶部薄膜覆盖的区域 (x0, y0, x1, y1)，满幅。

    验收脚本（①④）会把这个矩形排除在「内容」之外：它是固定的背景件，
    不是这一场画出来的东西。标题落在里面的位置由 ⑥ audit_text_band 单独查。
    """
    return (0, 0, W, int(L.CONTENT[1] - 30))


def scrim_top(height: int | None = None, strength: int = 210) -> Image.Image:
    """顶部深色渐隐薄膜：照片底上标题也读得清。按高度缓存，别每帧算。"""
    h = int(height or (L.CONTENT[1] - 30))
    if h in _SCRIM_CACHE:
        return _SCRIM_CACHE[h]
    grad = vertical_gradient(W * 2, h * 2, (6, 10, 16, strength), (6, 10, 16, 0))
    _SCRIM_CACHE[h] = grad
    return grad


def scene_head(c: Canvas, key, t: float, t_in: float = 0.30, dur: float = 0.50,
               scrim: bool = True) -> None:
    """画标题层：左侧琥珀竖条 + 一行标题（44 Bold 米白）+ 可选副标（25 冷灰）。

    参数
        key   场景文件主干（`s07_55cents`），文案从 `TEXT` 里取；
              也可以直接传 `("标题", "副标")` 临时覆盖。
        t     场景内秒数（已经过 `L.lead()` 的话就是提前后的时间）。
        t_in  入场时刻。铁律：新元素贴在台词起点，视觉略领先。
    `KOUBO_TITLE=light` 只画标题；`off` 整层不画（给用户看纯图版）。

    落区由 `layout.TITLE_BAND` 决定（corner 是 y 254–360），永不进字幕带。
    """
    if TITLE_MODE == "off":
        return
    if isinstance(key, (tuple, list)):
        title, sub = (key + ("",))[:2]
    else:
        title, sub = title_for(str(key))
    if not title:
        return

    top, bottom = L.TITLE_BAND
    a = stage(t, t_in, dur)
    if a <= 0:
        return

    if scrim:
        c.composite(scrim_top(), opacity=min(1.0, a * 1.4))

    # 左侧 5px 琥珀竖条：从上往下长出来
    bar_h = 46 * stage(t, t_in, dur * 0.7)
    c.rect((X, top + 4, X + 5, top + 4 + bar_h), fill=C.amber, opacity=a)

    # 标题：先垫一层 55% 黑影，照片底上也读得清
    ty = top - 6
    c.text(X + 22 + 2, ty + 3, title, "yh_b", 44, (0, 0, 0, 255), opacity=a * 0.55)
    dy = (1 - ease_out_cubic(a)) * 10
    c.text(X + 22, ty + dy, title, "yh_b", 44, C.text, opacity=a)

    if TITLE_MODE == "light" or not sub or bottom - top < 100:
        return

    sa = stage(t, t_in + 0.12, dur)
    if sa <= 0:
        return
    sy = top + 58 + (1 - ease_out_cubic(sa)) * 8
    c.text(X + 22, sy, sub, "yh", 25, C.text_dim, opacity=sa, tracking=1)


# ---------------------------------------------------------------- 图形

def bar(c: Canvas, t: float, x: float, y: float, w: float, h: float, frac: float,
        color, t_in: float = 0.0, dur: float = 0.8, bg_color=(127, 166, 201, 28),
        radius: int | None = None):
    """水平条形：先画底槽，再画填充。frac 0..1。"""
    radius = h // 2 if radius is None else radius
    a = stage(t, t_in, 0.2)
    if a <= 0:
        return
    c.rounded_rect((x, y, x + w, y + h), radius, fill=bg_color, opacity=a)
    p = stage(t, t_in, dur, ease_in_out_cubic)
    if p > 0:
        c.rounded_rect((x, y, x + max(h * 0.6, w * frac * p), y + h), radius,
                       fill=color, opacity=a)


def vbar(c: Canvas, t: float, x: float, y_bottom: float, w: float, h_max: float,
         frac: float, color, t_in: float = 0.0, dur: float = 0.9):
    """竖向柱：从底部长上来。"""
    p = stage(t, t_in, dur, ease_out_cubic)
    if p <= 0:
        return
    h = h_max * frac * p
    c.rect((x, y_bottom - h, x + w, y_bottom), fill=color)


def arrow(c: Canvas, t: float, p0, p1, color=None, width: int = 5, head: int = 20,
          t_in: float = 0.0, dur: float = 0.5):
    """直线箭头，按进度画出来。"""
    p = stage(t, t_in, dur, ease_in_out_cubic)
    if p <= 0.02:
        return
    color = color or C.cold
    x0, y0 = p0
    x1, y1 = (lerp(p0[0], p1[0], p), lerp(p0[1], p1[1], p))
    c.line([(x0, y0), (x1, y1)], color, width=width)
    import math
    ang = math.atan2(y1 - y0, x1 - x0)
    for s in (+1, -1):
        a2 = ang + s * 2.6
        c.line([(x1, y1), (x1 + head * math.cos(a2), y1 + head * math.sin(a2))],
               color, width=width)


def pill(c: Canvas, t: float, x: float, y: float, text: str, size: int = 32,
         fg=None, bg=None, t_in: float = 0.0, pad: int = 22, h: int = 56):
    a = stage(t, t_in, 0.35)
    if a <= 0:
        return
    fg = fg or C.text
    bg = bg or (127, 166, 201, 34)
    w = len(text) * size * 1.02 + pad * 2
    c.rounded_rect((x, y, x + w, y + h), h // 2, fill=bg, opacity=a)
    c.text(x + pad, y + (h - size) / 2 - 2, text, "yh", size, fg, opacity=a)


def cross(c: Canvas, t: float, cx: float, cy: float, r: float, color=None,
          t_in: float = 0.0, dur: float = 0.45, width: int = 8):
    """打叉：两条线交叉长出来。"""
    p = stage(t, t_in, dur, ease_out_cubic)
    if p <= 0:
        return
    color = color or C.danger
    d = r * p
    c.line([(cx - d, cy - d), (cx + d, cy + d)], color, width=width)
    c.line([(cx - d, cy + d), (cx + d, cy - d)], color, width=width)


def check(c: Canvas, t: float, cx: float, cy: float, r: float, color=None,
          t_in: float = 0.0, dur: float = 0.45, width: int = 8):
    p = stage(t, t_in, dur, ease_out_cubic)
    if p <= 0:
        return
    color = color or C.cold
    # 两段折线，第二段在 p>0.4 后画
    p1 = clamp(p / 0.45)
    c.line([(cx - r, cy), (cx - r + r * 0.75 * p1, cy + r * 0.75 * p1)], color, width=width)
    if p > 0.45:
        p2 = clamp((p - 0.45) / 0.55)
        c.line([(cx - r + r * 0.75, cy + r * 0.75),
                (cx - r + r * 0.75 + (r * 1.35) * p2, cy + r * 0.75 - r * 1.55 * p2)],
               color, width=width)


def strike(c: Canvas, t: float, x0: float, x1: float, y: float, color=None,
           t_in: float = 0.0, dur: float = 0.40, width: int = 5):
    """删除线。"""
    p = stage(t, t_in, dur, ease_in_out_cubic)
    if p <= 0:
        return
    color = color or C.danger
    c.line([(x0, y), (x0 + (x1 - x0) * p, y)], color, width=width)


def shake(t: float, t0: float, amp: float = 10, dur: float = 0.45) -> tuple[float, float]:
    """撞击抖动，返回 (dx, dy)。"""
    if t < t0 or t > t0 + dur:
        return (0.0, 0.0)
    k = 1 - (t - t0) / dur
    import math
    return (math.sin((t - t0) * 90) * amp * k, math.cos((t - t0) * 70) * amp * 0.6 * k)


def card(c: Canvas, t: float, box, fill=None, stroke=None, radius: int = 18,
         t_in: float = 0.0, alpha: float = 1.0):
    a = stage(t, t_in, 0.35) * alpha
    if a <= 0:
        return
    c.rounded_rect(box, radius, fill=fill or (22, 32, 46, 235),
                   outline=stroke or (127, 166, 201, 45), width=2, opacity=a)


def dim(c: Canvas, alpha: float = 0.55):
    """压暗整屏，用于聚焦某一块。"""
    if alpha <= 0:
        return
    c.rect((0, 0, W, H), fill=(6, 10, 16, int(255 * alpha)))


def letter_card(c: Canvas, box, letter: str, sub: str = "", t_in: float = 0.0,
                alpha: float = 1.0, color=None) -> None:
    """首字母灰卡：没有授权真人图时的标准替身。

    「配图即指控」——查不到、拿不到授权的人物，宁可上一张灰卡，也不要配错人。
    卡面只有首字母 + 一行小字（机构/头衔），不伪造肖像。

        K.letter_card(c, (X, 520, X + 420, 940), "N", "NVIDIA · 供应商", t_in=1.2)
    """
    a = stage(t, t_in, 0.40) * alpha
    if a <= 0:
        return
    x0, y0, x1, y1 = box
    c.rounded_rect(box, 20, fill=(28, 38, 52, 235), outline=(127, 166, 201, 70),
                   width=2, opacity=a)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    c.text(cx, cy - 10, letter[:2], "yh_b", int((y1 - y0) * 0.38), color or C.text_dim,
           anchor="mm", opacity=a * 0.9)
    if sub:
        c.text(cx, y1 - 40, sub, "yh", 24, C.text_dim, anchor="mm", opacity=a * 0.9)
