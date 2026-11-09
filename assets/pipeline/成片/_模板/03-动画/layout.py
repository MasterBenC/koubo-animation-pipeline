# -*- coding: utf-8 -*-
"""版式：1080x1920 竖屏，圆形头像画中画 + 动画主画面。

所有坐标都是「成片像素」，唯一真源。渲染、合成、验收全部引这里，改一处全对。

圆形头像（用户最终确认的参数，参照参考图）：
    直径 280，圆心 (840, 1555)
    -> 包围盒 [700, 1415, 980, 1695]
    -> 右边距 100，下边距 225（贴住抖音底部信息条上沿，不能再低）
    白边 2px，蒙版羽化 10，阴影向下偏移
    头部在源画幅里是实测的（6 帧几乎不动）：
        头顶 29% / 下巴 49% / 左 33% / 右 61%
        -> 头中心 (507, 749)，取 (507, 748)
        裁剪框 440 -> 头高 384 占 87%，留一点呼吸又不空

字幕带（用户后期烧，我们一层都不能进）：
    底部居中，基线距底 460-620  ->  成片 y 1300-1460

内容栅格：
    CONTENT  936×890  x 72-1008, y 400-1290
    圆右侧只在 y 1200-1420 / x 720-940 这一小块禁区
"""
from __future__ import annotations

W, H = 1080, 1920

# 平台安全区（抖音按钮、底部信息条）
SAFE = dict(top=140, right=72, bottom=460, left=60)

# ---------------- 人物画中画：圆形头像
PIP_CX, PIP_CY, PIP_R = 840, 1555, 140
PIP = (PIP_CX - PIP_R, PIP_CY - PIP_R, PIP_CX + PIP_R, PIP_CY + PIP_R)   # 700,1415,980,1695
PIP_W = PIP[2] - PIP[0]          # 220
PIP_H = PIP[3] - PIP[1]          # 220
PIP_RADIUS = PIP_R               # 半径=圆角，画出来就是正圆
PIP_BORDER = 2                   # 白色描边
PIP_FEATHER = 10                 # 蒙版羽化（像素）
PIP_SHADOW = 22                  # 阴影模糊半径
PIP_SHADOW_OFFSET = (0, 10)      # 阴影向下偏移
PIP_SHADOW_ALPHA = 120

# 从人物帧里裁出来的正方形边长（源画幅坐标）
HEAD_BOX = 520
HEAD_CX, HEAD_CY = 570, 838

# ---------------- 动画可用区
CONTENT_TOP = 200                # 顶部标题带下沿
CONTENT_BOTTOM = 1290            # 字幕带上沿
CONTENT_LEFT = 60
CONTENT_RIGHT = 1020

CONTENT = (72, 400, 1008, 1290)          # 主内容区：936×890

# 字幕带（后期字幕所在，内容一律不得进入）
SUBTITLE_BAND = (1300, 1460)

# 段落状态：'full' 全屏 / 'pip' 缩角
# 时间轴为成片时间（已扣掉 34.09s 的删除）
PIP_ENTER = 0.70                 # 全屏->缩角 过渡时长
PIP_EXIT = 0.55                  # 缩角->全屏 过渡时长
PIP_POP = 0.40                   # 缩角落定后的缩放入场

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
# 起止是成片时间；场景内部时间 = t - 起
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

# 动画场景时间槽（成片时间），每个场景只在自己的槽里渲染
BEATS = []  # 由 build_timeline.py 填充


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
    """0 = 直角（全屏），1 = 正圆。中间是圆角矩形，过渡就是"圆慢慢长出来"。"""
    e = _ease(progress)
    return int(round(PIP_R * e))


def pip_feather(progress: float) -> float:
    """羽化跟着圆角一起长出来，全屏时没有羽化。"""
    return PIP_FEATHER * _ease(progress)


def pip_params(progress: float):
    """一次拿齐 (裁切矩形, 落位矩形, 圆角, 羽化)。progress=1 就是圆头像。"""
    return pip_crop(progress), pip_rect(progress), pip_radius(progress), pip_feather(progress)


def rect_hits_content(rect, pad=8) -> bool:
    """动画内容是否侵入人物框（含 pad）。验收用。"""
    x0, y0, x1, y1 = rect
    return not (x1 + pad < PIP[0] or x0 - pad > PIP[2] or y1 + pad < PIP[1] or y0 - pad > PIP[3])


def circle_hits(px: float, py: float, pad: float = 6) -> bool:
    """某个内容像素是否落进头像圆（含 pad）。验收用。"""
    return (px - PIP_CX) ** 2 + (py - PIP_CY) ** 2 <= (PIP_R + pad) ** 2
