# -*- coding: utf-8 -*-
"""版式：按 (方向, 画中画模式) 取一整套坐标。唯一真源。

所有坐标都是「成片像素」。渲染、合成、验收全部引这里，改一处全对。

## 四种模式

    portrait / corner   竖屏 9:16 + 右下角圆头像        默认，口播-01 用这个（已验证）
    portrait / cut      竖屏 9:16 + 人与动画互切        几何已定，状态机待实现
    landscape / corner  横屏 16:9 + 右下角卡片          等模板
    landscape / cut     横屏 16:9 + 人与动画互切        等模板

切换：环境变量 `LAYOUT_PROFILE="portrait/cut"`，或 `layout.activate("portrait/cut")`。

> 默认值必须和重构前逐像素一致。改这里之前先跑基线帧比对。

## 竖屏 / 右下角（默认，已验证）

    圆头像 直径 280，圆心 (840,1555) -> 包围盒 [700,1415,980,1695]
    右边距 100，下边距 345；白边 2px，羽化 10，阴影 (0,10) 模糊 22
    头部实测（6 帧几乎不动）：头顶 29% / 下巴 49% / 左 33% / 右 61%
    裁剪框 520 @ (570,838) —— 覆盖全片最大偏移，换人必须重标

## 内容栅格

    CONTENT  936×890   x 72-1008, y 400-1290
    字幕带   y 1300-1460（用户后期烧，一个像素都不许进）
"""
from __future__ import annotations

import os

# ============================================================ 模式表

PROFILES: dict[str, dict] = {
    # ---------------- 竖屏 + 右下角圆头像（已验证）
    "portrait/corner": dict(
        status="ready",
        mode="corner",
        size=(1080, 1920),
        safe=dict(top=140, right=72, bottom=460, left=60),
        content=(72, 400, 1008, 1290),
        subtitle_band=(1300, 1460),
        pip=dict(cx=840, cy=1555, r=140, border=2, feather=10.0,
                 shadow=22, shadow_offset=(0, 10), shadow_alpha=120),
        head=dict(box=520, cx=570, cy=838),
        enter=0.70, exit=0.55, pop=0.40,
    ),

    # ---------------- 竖屏 + 人与动画互切（几何已定，状态机待实现）
    # 没有圆头像，动画出镜时能用满 y 220-1290（比 corner 高 300px）
    "portrait/cut": dict(
        status="geometry-ready",
        mode="cut",
        size=(1080, 1920),
        safe=dict(top=140, right=72, bottom=460, left=60),
        content=(72, 220, 1008, 1290),
        subtitle_band=(1300, 1460),
        pip=None,
        head=dict(box=520, cx=570, cy=838),   # 互切时人物全屏，此值仅备用
        enter=0.0, exit=0.0, pop=0.0,
    ),

    # ---------------- 横屏 16:9（等用户给模板，参数留空）
    "landscape/corner": dict(
        status="todo", mode="corner", size=(1920, 1080),
        safe=None, content=None, subtitle_band=None,
        pip=None, head=None, enter=0.0, exit=0.0, pop=0.0,
    ),
    "landscape/cut": dict(
        status="todo", mode="cut", size=(1920, 1080),
        safe=None, content=None, subtitle_band=None,
        pip=None, head=None, enter=0.0, exit=0.0, pop=0.0,
    ),
}

DEFAULT_PROFILE = "portrait/corner"
ACTIVE_PROFILE = DEFAULT_PROFILE
MODE = "corner"


def available() -> list[str]:
    return [k for k, v in PROFILES.items() if v["status"] != "todo"]


def activate(name: str) -> None:
    """切换模式并重算全部模块级常量。"""
    global ACTIVE_PROFILE, MODE, W, H, SAFE, CONTENT, SUBTITLE_BAND
    global CONTENT_TOP, CONTENT_BOTTOM, CONTENT_LEFT, CONTENT_RIGHT
    global PIP_CX, PIP_CY, PIP_R, PIP, PIP_W, PIP_H, PIP_RADIUS
    global PIP_BORDER, PIP_FEATHER, PIP_SHADOW, PIP_SHADOW_OFFSET, PIP_SHADOW_ALPHA
    global HEAD_BOX, HEAD_CX, HEAD_CY, PIP_ENTER, PIP_EXIT, PIP_POP

    key = name.replace(" ", "").replace("-", "/").lower()
    if key not in PROFILES:
        raise KeyError(f"未知版式 {name!r}；可选：{', '.join(PROFILES)}")
    p = PROFILES[key]
    if p["status"] == "todo":
        raise NotImplementedError(
            f"版式 {key} 参数还没定（等横屏模板）。当前可用：{', '.join(available())}")

    ACTIVE_PROFILE = key
    MODE = p["mode"]
    W, H = p["size"]
    SAFE = p["safe"]
    CONTENT = p["content"]
    SUBTITLE_BAND = p["subtitle_band"]
    CONTENT_LEFT, CONTENT_TOP, CONTENT_RIGHT, CONTENT_BOTTOM = CONTENT

    if p["pip"]:
        d = p["pip"]
        PIP_CX, PIP_CY, PIP_R = d["cx"], d["cy"], d["r"]
        PIP_BORDER = d["border"]
        PIP_FEATHER = d["feather"]
        PIP_SHADOW = d["shadow"]
        PIP_SHADOW_OFFSET = d["shadow_offset"]
        PIP_SHADOW_ALPHA = d["shadow_alpha"]
    else:
        PIP_CX = PIP_CY = PIP_R = 0
        PIP_BORDER = 0
        PIP_FEATHER = 0.0
        PIP_SHADOW = 0
        PIP_SHADOW_OFFSET = (0, 0)
        PIP_SHADOW_ALPHA = 0

    PIP = (PIP_CX - PIP_R, PIP_CY - PIP_R, PIP_CX + PIP_R, PIP_CY + PIP_R)
    PIP_W = PIP_H = 2 * PIP_R
    PIP_RADIUS = PIP_R

    h = p["head"]
    HEAD_BOX, HEAD_CX, HEAD_CY = (h["box"], h["cx"], h["cy"]) if h else (0, 0, 0)

    PIP_ENTER, PIP_EXIT, PIP_POP = p["enter"], p["exit"], p["pop"]


# ============================================================ 时间轴（本片专用）

# 段落状态：'full' 全屏 / 'pip' 缩角（cut 模式下语义不同，见 references/modes.md）
SCHEDULE = [
    (0.00, 13.35, "full"),       # 钩子1：807 亿
    (13.35, 25.90, "pip"),       # 钩子2：估值 2万亿→1.5万亿
    (25.90, 29.85, "full"),      # 片头口号，必须露脸
    (29.85, 107.05, "pip"),      # 片头引言 + 第一层
    (107.05, 111.00, "full"),    # 转场：再往深处拆
    (111.00, 156.60, "pip"),     # 第二层
    (156.60, 159.80, "full"),    # 转场：闭环露出来了
    (159.80, 244.85, "pip"),     # 闭环 + 第三层 + 收束
    (244.85, 264.36, "full"),    # 下期 + CTA
]

# 场景槽位：(编号, 文件名主干, 起, 止, DURATION)
SCENE_SLOTS = [
    ("S01", "s01_valuation_haircut", 13.35, 25.90, 12.55),
    ("S02", "s02_cutaway", 29.85, 38.70, 8.85),
    ("S03", "s03_ledger_807", 38.70, 45.35, 6.65),
    ("S04", "s04_smokescreen", 45.35, 55.10, 9.75),
    ("S05", "s05_tear_report", 55.10, 63.70, 8.60),
    ("S06", "s06_marginal_cost", 63.70, 72.20, 8.50),
    ("S07", "s07_55cents", 72.20, 85.10, 12.90),
    ("S08", "s08_39vs45", 85.10, 96.20, 11.10),
    ("S09", "s09_one_more_card", 96.20, 107.05, 10.85),
    ("S10", "s10_footnotes", 111.00, 122.50, 11.50),
    ("S11", "s11_contract", 122.50, 140.25, 17.75),
    ("S12", "s12_irrevocable", 140.25, 156.25, 16.00),
    ("S13", "s13_loop", 159.80, 177.20, 17.40),
    ("S14", "s14_pressure", 183.40, 202.65, 19.25),
    ("S15", "s15_dump", 202.65, 213.35, 10.70),
    ("S16", "s16_close", 213.35, 244.85, 31.50),
]

BEATS = []  # 由 build_timeline.py 填充


# ============================================================ 状态与几何

def state_at(t: float) -> tuple[str, float]:
    """返回 (状态, 该状态内的归一化进度)。过渡期返回渐变进度 0..1。"""
    for i, (a, b, s) in enumerate(SCHEDULE):
        if t < a:
            continue
        if t <= b:
            nxt = SCHEDULE[i + 1][2] if i + 1 < len(SCHEDULE) else s
            if s == "full" and nxt == "pip" and t > b - PIP_ENTER:
                return ("to_pip", (t - (b - PIP_ENTER)) / PIP_ENTER)
            if s == "pip" and nxt == "full" and t > b - PIP_EXIT:
                return ("to_full", (t - (b - PIP_EXIT)) / PIP_EXIT)
            return (s, 1.0)
    return ("full", 1.0)


def _ease(p: float) -> float:
    """先快后慢的缩退：位移和尺寸同步，避免"脸先跳过去"。"""
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def pip_rect(progress: float) -> tuple[float, float, float, float]:
    """0 = 全屏，1 = 圆头像。返回人物**落位**的矩形（浮点，允许超出画布）。"""
    e = _ease(progress)
    x0 = 0 + (PIP[0] - 0) * e
    y0 = 0 + (PIP[1] - 0) * e
    x1 = W + (PIP[2] - W) * e
    y1 = H + (PIP[3] - H) * e
    return (x0, y0, x1, y1)


def pip_crop(progress: float) -> tuple[float, float, float, float]:
    """0 = 全屏（整幅人物），1 = 圆头像（只裁头部 HEAD_BOX 见方）。"""
    e = _ease(progress)
    hb = HEAD_BOX / 2
    cx0, cy0 = HEAD_CX - hb, HEAD_CY - hb
    return (0 + cx0 * e, 0 + cy0 * e,
            W + (HEAD_CX + hb - W) * e, H + (HEAD_CY + hb - H) * e)


def pip_radius(progress: float) -> int:
    """0 = 直角（全屏），1 = 正圆。中间是圆角矩形，"圆慢慢长出来"。"""
    return int(round(PIP_R * _ease(progress)))


def pip_feather(progress: float) -> float:
    """羽化跟着圆角一起长出来，全屏时没有羽化。"""
    return PIP_FEATHER * _ease(progress)


def pip_params(progress: float):
    """一次拿齐 (裁切矩形, 落位矩形, 圆角, 羽化)。progress=1 就是圆头像。"""
    if MODE != "corner":
        raise NotImplementedError(
            f"当前模式 {ACTIVE_PROFILE} 不是画中画模式，没有 pip_params；"
            "互切模式请用 cut_params()（待实现）")
    return pip_crop(progress), pip_rect(progress), pip_radius(progress), pip_feather(progress)


def rect_hits_content(rect, pad=8) -> bool:
    """动画内容是否侵入人物框（含 pad）。验收用。"""
    x0, y0, x1, y1 = rect
    return not (x1 + pad < PIP[0] or x0 - pad > PIP[2] or y1 + pad < PIP[1] or y0 - pad > PIP[3])


def circle_hits(px: float, py: float, pad: float = 6) -> bool:
    """某个内容像素是否落进头像圆（含 pad）。验收用。"""
    if PIP_R <= 0:
        return False
    return (px - PIP_CX) ** 2 + (py - PIP_CY) ** 2 <= (PIP_R + pad) ** 2


# ============================================================ 启动时激活

activate(os.environ.get("LAYOUT_PROFILE", DEFAULT_PROFILE))
