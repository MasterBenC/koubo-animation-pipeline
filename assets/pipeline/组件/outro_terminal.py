# -*- coding: utf-8 -*-
"""OutroTerminalSpoof · 「终端报错欺诈流」通用片尾组件。

在一段视频的最后一帧上，叠一层毛玻璃暗化遮罩 + 赛博终端弹窗，
用"系统权限拦截"的假故障包装"双击点赞"的引导，冷幽默反差。

结构：**开头先定格 0.5 秒的完整页面**（让观众读得完，首尾同帧），
然后再播 1.5 秒的故障重演动画，最后回到同一张完整页面。总长 2.0 秒。
用 --hold 0 可退回纯 1.5 秒版本；--hold-at tail 可改成结尾定格。

用法（三种）：

  1) 只出组件本身（默认从视频最后一帧取底）：
     python outro_terminal.py --base ..\\..\\02-剪辑\\05-成片.mp4 --out outro.mp4

  2) 自定义文案（组件可复用）：
     python outro_terminal.py --base 05-成片.mp4 --out outro.mp4 \\
         --warning "> [警告] 检测到白嫖行为，本地算力余额不足！"

  3) 直接拼到正片末尾：
     python outro_terminal.py --attach 05-成片.mp4 --out 06-成片带片尾.mp4

设计参数全部集中在 OutroConfig 里，改文案/配色不用动渲染逻辑。
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ============================================================ 常量

W, H = 1080, 1920
SS = 2                      # 超采样倍数：2x 渲染再缩回，文字边缘才干净
FPS = 30
DURATION = 1.5
FRAMES = int(round(FPS * DURATION))     # 45（动画本身）
HOLD_FRAMES = 15                        # 默认 0.5s 定格，由 cfg.hold 覆盖

CYAN = (0, 240, 255)
RED = (255, 51, 102)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BOX_BG = (10, 15, 20)
MASK_RGB = (8, 12, 16)
YELLOW = (255, 214, 0)
DIM = (118, 138, 156)

FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FONT_FILES = {
    "mono": "consola.ttf",
    "mono_b": "consolab.ttf",
    "cjk_b": "msyhbd.ttc",
    "cjk": "msyh.ttc",
}
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONT_DIR / FONT_FILES[name]), size)
    return _font_cache[key]


# ============================================================ 配置

@dataclass
class OutroConfig:
    """组件对外暴露的全部可调参数。"""

    warning_text: str = "> [警告] 检测到白嫖行为，本地算力余额不足！"
    cta_text: str = "> 请立即【双击屏幕】注入点赞，完成档案签收 _"
    log_text: str = "> 正在为您归档本期【财富底牌图纸】..."
    progress_text: str = "[99%]"
    status_text: str = "[ SYSTEM_INTERCEPT // MUJIE_ARCH_V2.6 ]"
    brand_text: str = "拆解师Ben · 沐杰架构"
    highlight: str = "双击屏幕"          # CTA 里要高亮的那段
    box_w: int = 860
    box_pad: int = 40
    box_center_y: float = 0.45
    accent: tuple = CYAN
    warn: tuple = RED
    border_w: int = 2
    radius: int = 10
    mask_alpha: float = 0.88
    mask_blur: float = 12.0
    hold: float = 0.5            # 定格时长：让观众读得完整张弹窗
    hold_at: str = "head"        # "head"=开头先给完整页再演动画；"tail"=动画后定格
    audio: bool = True


# ============================================================ 文字排版

def char_font(ch: str, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """ASCII 走等宽字体，中文走雅黑粗体——混排必须手动切。"""
    if ord(ch) < 128:
        return font("mono_b" if bold else "mono", size)
    return font("cjk_b" if bold else "cjk", size)


def measure(s: str, size: int, bold: bool = True) -> float:
    return sum(char_font(ch, size, bold).getlength(ch) for ch in s)


def rebalance(lines: list[str], min_last: int = 4) -> list[str]:
    """避免最后一行只剩一两个字（中文断行的典型丑相）。"""
    if len(lines) < 2:
        return lines
    out = list(lines)
    while len(out) >= 2 and len(out[-1]) < min_last and len(out[-2]) > min_last:
        out[-1] = out[-2][-1] + out[-1]
        out[-2] = out[-2][:-1]
    return out


def wrap(text: str, size: int, max_w: float, bold: bool = True) -> list[str]:
    """按像素折行。只在**英文单词**上按空格断，中文按字断。"""
    lines: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if not cur or measure(trial, size, bold) <= max_w:
            cur = trial
            continue
        # 仅当当前是 ASCII 字母数字、且上一段也是 ASCII 时，才回退到空格断词
        if (ch.isascii() and ch.isalnum() and cur and cur[-1].isascii()
                and cur[-1].isalnum() and " " in cur):
            cut = cur.rfind(" ")
            lines.append(cur[:cut])
            cur = cur[cut + 1:] + ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return rebalance(lines)


def resolve_highlight(text: str, wanted: str) -> str:
    """高亮词兜底：先用配置的，没有就从【】里取，再没有就取『』。"""
    if wanted and wanted in text:
        return wanted
    for lb, rb in (("【", "】"), ("『", "』"), ("[", "]")):
        i = text.find(lb)
        j = text.find(rb, i + 1)
        if 0 <= i < j:
            return text[i + 1:j]
    return ""


def draw_mixed(d: ImageDraw.ImageDraw, x: float, y: float, text: str, size: int,
               fill, bold: bool = True, tracking: float = 0.0) -> list[tuple]:
    """逐字画混排文字；fill 可以是颜色，也可以是按字索引取色的函数。"""
    boxes = []
    cx = x
    for i, ch in enumerate(text):
        f = char_font(ch, size, bold)
        color = fill(i) if callable(fill) else fill
        d.text((cx, y), ch, font=f, fill=color, anchor="ls")
        adv = f.getlength(ch) + tracking
        boxes.append((cx, cx + adv))
        cx += adv
    return boxes


def draw_line_hl(d: ImageDraw.ImageDraw, x: float, y: float, text: str, size: int,
                 base=WHITE, hl_bg=YELLOW, hl_fg=BLACK,
                 hl_from: int = -1, hl_to: int = -1, bold: bool = True) -> list[tuple]:
    """画一行，可选把 [hl_from, hl_to) 这段做成"黄底黑字"高亮块。"""
    boxes = []
    cx = x
    for ch in text:
        f = char_font(ch, size, bold)
        adv = f.getlength(ch)
        boxes.append((cx, cx + adv))
        cx += adv

    if hl_from >= 0 and hl_to > hl_from and hl_from < len(boxes):
        hx0 = boxes[hl_from][0] - 4
        hx1 = boxes[min(hl_to, len(boxes)) - 1][1] + 4
        d.rectangle([hx0, y - size * 0.94, hx1, y + size * 0.26], fill=hl_bg + (240,))

    for i, ch in enumerate(text):
        f = char_font(ch, size, bold)
        inside = hl_from >= 0 and hl_from <= i < hl_to
        d.text((boxes[i][0], y), ch, font=f, fill=(hl_fg if inside else base) + (255,),
               anchor="ls")
    return boxes


# ============================================================ 底图

def extract_last_frame(src: Path, out_png: Path) -> None:
    if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        shutil.copyfile(src, out_png)
        return
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-sseof", "-0.2", "-i", str(src), "-vsync", "0",
        "-frames:v", "1", "-update", "1", str(out_png),
    ], check=True)


def build_backdrop(last_frame: Image.Image, cfg: OutroConfig) -> Image.Image:
    base = last_frame.convert("RGB").resize((W * SS, H * SS), Image.LANCZOS)
    blurred = base.filter(ImageFilter.GaussianBlur(cfg.mask_blur * SS))
    dark = Image.new("RGB", blurred.size, MASK_RGB)
    return Image.blend(blurred, dark, cfg.mask_alpha)


def chromatic(image: Image.Image, dx: int) -> Image.Image:
    if dx == 0:
        return image
    r, g, b = image.split()
    return Image.merge("RGB", (ImageChops.offset(r, dx, 0), g, ImageChops.offset(b, -dx, 0)))


def glitch_slices(image: Image.Image, f: int) -> Image.Image:
    """前两帧的水平切片错位，模拟信号被打断。"""
    if f > 1:
        return image
    out = image.copy()
    bands = [(0.18, 92), (0.31, -140), (0.52, 60), (0.66, -38)] if f == 0 \
        else [(0.24, -64), (0.44, 110), (0.71, -26)]
    for frac, dx in bands:
        y0 = int(H * frac)
        h = 46 if f == 0 else 28
        band = out.crop((0, y0, W, min(H, y0 + h)))
        out.paste(band, (dx, y0))
    return out


# ============================================================ 8-bit 像素红心

HEART = [
    "01100110",
    "11111111",
    "11111111",
    "11111111",
    "01111110",
    "00111100",
    "00011000",
]


def draw_pixel_heart(d: ImageDraw.ImageDraw, cx: float, cy: float, cell: float,
                     color: tuple, glow: float = 0.0) -> None:
    rows, cols = len(HEART), len(HEART[0])
    ox = cx - cols * cell / 2
    oy = cy - rows * cell / 2
    if glow > 0:
        halo = tuple(int(c * glow) for c in color) + (255,)
        for r, row in enumerate(HEART):
            for c, v in enumerate(row):
                if v == "1":
                    d.rectangle([ox + c * cell - cell * 0.55, oy + r * cell - cell * 0.55,
                                 ox + (c + 1) * cell + cell * 0.55,
                                 oy + (r + 1) * cell + cell * 0.55], fill=halo)
    for r, row in enumerate(HEART):
        for c, v in enumerate(row):
            if v == "1":
                d.rectangle([ox + c * cell, oy + r * cell,
                             ox + (c + 1) * cell - 1, oy + (r + 1) * cell - 1],
                            fill=color + (255,))


# ============================================================ 版面

@dataclass
class Layout:
    box: tuple
    status_h: float
    log_lines: list = field(default_factory=list)
    warn_lines: list = field(default_factory=list)
    cta_lines: list = field(default_factory=list)
    line_y: dict = field(default_factory=dict)

    SZ_LOG = 32
    SZ_WARN = 34
    SZ_CTA = 38
    LH_LOG = 48
    LH_WARN = 52
    LH_CTA = 56


def layout_of(cfg: OutroConfig) -> Layout:
    inner = cfg.box_w - cfg.box_pad * 2
    log_lines = wrap(cfg.log_text + " " + cfg.progress_text, Layout.SZ_LOG, inner)
    warn_lines = wrap(cfg.warning_text, Layout.SZ_WARN, inner)
    cta_lines = wrap(cfg.cta_text, Layout.SZ_CTA, inner)

    status_h = 36
    gap_status = 34
    gap_lw, gap_wc = 24, 24
    bottom_pad = 62          # 红心 + 品牌角标的高度

    h = (status_h + gap_status
         + Layout.LH_LOG * len(log_lines) + gap_lw
         + Layout.LH_WARN * len(warn_lines) + gap_wc
         + Layout.LH_CTA * len(cta_lines)
         + bottom_pad + cfg.box_pad)

    x0 = (W - cfg.box_w) / 2
    top = cfg.box_center_y * H - h / 2

    y = top + status_h + gap_status + Layout.LH_LOG * 0.74
    ly = {}
    for i in range(len(log_lines)):
        ly[f"log{i}"] = y
        y += Layout.LH_LOG
    y += gap_lw - (Layout.LH_LOG - Layout.LH_LOG * 0.74)
    for i in range(len(warn_lines)):
        ly[f"warn{i}"] = y
        y += Layout.LH_WARN
    y += gap_wc - (Layout.LH_WARN - Layout.LH_WARN * 0.74)
    for i in range(len(cta_lines)):
        ly[f"cta{i}"] = y
        y += Layout.LH_CTA

    return Layout(box=(x0, top, x0 + cfg.box_w, top + h), status_h=status_h,
                  log_lines=log_lines, warn_lines=warn_lines, cta_lines=cta_lines,
                  line_y=ly)


# ============================================================ 单帧

def typewriter(text: str, f: int, f0: int, f1: int) -> str:
    if f < f0:
        return ""
    if f >= f1:
        return text
    return text[:max(0, int(round(len(text) * (f - f0) / max(1, f1 - f0))))]


def render_frame(backdrop: Image.Image, f: int, cfg: OutroConfig, lay: Layout,
                 clock: int | None = None) -> Image.Image:
    """f = 动画进度帧（决定内容长到哪一步）；clock = 真实帧号（决定光标闪、红心呼吸）。"""
    clock = f if clock is None else clock
    # 故障只作用在背景上：弹窗本身要干净地压上去，否则字会被切碎
    if f <= 1:
        img = chromatic(backdrop, 6 - f * 3)
        img = glitch_slices(img, f)
    else:
        img = backdrop.copy()
    d = ImageDraw.Draw(img, "RGBA")

    jitter = {0: 8, 1: -5, 2: 3, 3: -1}.get(f, 0) * SS
    x0, top, x1, bot = [v * SS for v in lay.box]
    x0 += jitter
    x1 += jitter

    # ---------- 边框颜色状态机：16 帧切警告红，17 帧闪一下
    at_warn = f >= 16
    if at_warn:
        accent = tuple(int(c * 0.40) for c in cfg.warn) if f == 17 else cfg.warn
    else:
        accent = cfg.accent

    # 外发光
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle([x0, top, x1, bot], radius=cfg.radius * SS,
                         outline=accent + (255,), width=3 * SS)
    glow = glow.filter(ImageFilter.GaussianBlur(16 * SS))
    k = 0.55 if at_warn else 0.38
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * k)))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    # 面板 + 边框
    d.rounded_rectangle([x0, top, x1, bot], radius=cfg.radius * SS, fill=BOX_BG + (255,))
    d.rounded_rectangle([x0, top, x1, bot], radius=cfg.radius * SS,
                        outline=accent + (255,), width=cfg.border_w * SS)

    # 状态条
    sh = lay.status_h * SS
    d.rectangle([x0 + cfg.border_w * SS, top + cfg.border_w * SS,
                 x1 - cfg.border_w * SS, top + sh], fill=accent + (255,))
    st = cfg.status_text
    st_size = 19 * SS
    st_w = measure(st, st_size, True)
    d.text((x0 + (x1 - x0 - st_w) / 2, top + sh - 9 * SS), st,
           font=font("mono_b", st_size), fill=BLACK + (255,), anchor="ls")

    bx = x0 + cfg.box_pad * SS

    # ---------- 日志行：f4-15 逐字打印
    log_all = " ".join(lay.log_lines)
    shown = typewriter(log_all, f, 4, 15)
    n = len(shown)
    acc = 0
    last_drawn = None
    for i, ln in enumerate(lay.log_lines):
        take = shown[acc: acc + len(ln)] if n > acc else ""
        acc += len(ln)
        if not take:
            break
        y = lay.line_y[f"log{i}"] * SS
        boxes = draw_mixed(d, bx, y, take, Layout.SZ_LOG * SS, CYAN + (255,), bold=False)
        last_drawn = (boxes[-1][1], y)

    if 4 <= f < 15 and last_drawn:
        cx, y = last_drawn
        d.rectangle([cx + 3 * SS, y - 30 * SS, cx + 15 * SS, y + 5 * SS], fill=CYAN + (235,))

    # ---------- 警告行：f16 起，第一帧轻微放大
    if f >= 16:
        base_k = 1.12 if f == 16 else (1.05 if f == 17 else 1.0)
        inner_px = (cfg.box_w - cfg.box_pad * 2) * SS
        for i, ln in enumerate(lay.warn_lines):
            y = lay.line_y[f"warn{i}"] * SS
            # 放大不能让它顶出内边距
            w0 = measure(ln, Layout.SZ_WARN * SS) or 1.0
            k = min(base_k, inner_px * 0.97 / w0)
            k = 1.0 if k < 1.005 else k
            if k == 1.0:
                draw_mixed(d, bx, y, ln, Layout.SZ_WARN * SS, cfg.warn + (255,))
            else:
                tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw_mixed(ImageDraw.Draw(tmp), bx, y, ln,
                           int(Layout.SZ_WARN * SS * k), cfg.warn + (255,))
                img = Image.alpha_composite(img.convert("RGBA"), tmp).convert("RGB")
                d = ImageDraw.Draw(img, "RGBA")

    # ---------- CTA：f29 起，黄底高亮 + 光标
    cursor = None
    if 16 <= f < 29:
        # 等待输入：真终端就是这个样子，顺便把下半部的空档填掉
        y = lay.line_y["cta0"] * SS
        draw_mixed(d, bx, y, ">", Layout.SZ_CTA * SS, DIM + (230,))
        if (f // 4) % 2 == 0:
            cx = bx + measure("> ", Layout.SZ_CTA * SS)
            d.rectangle([cx, y - 30 * SS, cx + 15 * SS, y + 6 * SS],
                        fill=DIM + (200,))
    if f >= 29:
        hl_word = resolve_highlight(cfg.cta_text, cfg.highlight)
        shown_cta = typewriter(cfg.cta_text, f, 29, 38)
        idx = 0
        for i, ln in enumerate(lay.cta_lines):
            if idx >= len(shown_cta):
                break
            take = shown_cta[idx: idx + len(ln)]
            idx += len(ln)
            y = lay.line_y[f"cta{i}"] * SS
            indent = 0.0 if take.lstrip().startswith(">") else measure("> ", Layout.SZ_CTA) * SS
            hpos = ln.find(hl_word) if hl_word else -1
            h_from = hpos if (hpos >= 0 and take) else -1
            h_to = (hpos + len(hl_word)) if h_from >= 0 else -1
            boxes = draw_line_hl(d, bx + indent, y, take, Layout.SZ_CTA * SS,
                                 base=WHITE, hl_bg=YELLOW, hl_fg=BLACK,
                                 hl_from=h_from, hl_to=h_to)
            if boxes:
                cursor = (boxes[-1][1] + 4 * SS, y)

    if cursor and (f < 38 or (clock // 3) % 2 == 0):
        cx, y = cursor
        d.rectangle([cx, y - 30 * SS, cx + 15 * SS, y + 6 * SS], fill=WHITE + (240,))

    # ---------- 红心 + 品牌
    if f >= 30:
        # 出现时略小，长到 1.0；之后一直做低频呼吸（定格阶段也不会僵住）
        grow = min(1.0, (f - 30) / 10.0)
        pulse = 1.0 + 0.11 * math.sin((clock - 30) / FPS * 2 * math.pi * 1.4)
        cell = 6.0 * SS * (0.86 + 0.14 * grow) * pulse
        right = x1 - cfg.box_pad * SS - 6 * SS
        hy = bot - cfg.box_pad * SS - 2.4 * cell
        hx = right - 4 * cell
        draw_pixel_heart(d, hx, hy, cell, RED, glow=0.28)

        bw = measure(cfg.brand_text, 20 * SS, False)
        d.text((hx - 4 * cell - 14 * SS - bw, hy + 8 * SS),
               cfg.brand_text, font=font("cjk", 20 * SS), fill=DIM + (215,), anchor="ls")

    out = img.resize((W, H), Image.LANCZOS)
    if f <= 1:
        # 交界处把整帧撕开（此时弹窗还是空的，撕它不会毁字）：
        # 从「完整页」切到「空终端」必须像系统被打断，而不是像渲染错了
        out = glitch_slices(out, f)
        out = chromatic(out, 5 - f * 2)
        flash = Image.new("RGB", out.size, (0, 240, 255))
        out = Image.blend(out, flash, 0.12 if f == 0 else 0.05)
    return out


# ============================================================ 音频

def synth_audio(path: Path, dur: float | None = None, sr: int = 48000,
                offset: float = 0.0) -> None:
    """offset = 音效整体后移秒数（定格在开头时，声音要等动画开始才响）。"""
    dur = DURATION if dur is None else dur
    n = int(sr * dur)
    buf = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(20261107)      # 固定种子，可复现

    def add(sig, at, gain=1.0):
        i = int((at + offset) * sr)
        m = min(len(sig), n - i)
        if m > 0:
            buf[i:i + m] += sig[:m] * gain

    # 0.0 电流切断
    k = int(0.20 * sr)
    t = np.arange(k) / sr
    swoop = np.sin(2 * np.pi * (420 * np.exp(-9 * t) + 40) * t) * np.exp(-t / 0.05)
    noise = rng.normal(0, 1, k) * np.exp(-t / 0.022)
    add((swoop * 0.7 + noise * 0.5).astype(np.float32), 0.0, 0.85)

    # 0.1-0.4 机械键盘 4 声
    for i, at in enumerate((0.12, 0.19, 0.26, 0.33)):
        k = int(0.035 * sr)
        t = np.arange(k) / sr
        click = (rng.normal(0, 1, k) * np.exp(-t / 0.006)
                 + np.sin(2 * np.pi * (1800 + i * 260) * t) * np.exp(-t / 0.012) * 0.5)
        add(click.astype(np.float32), at, 0.30)

    # 0.5 两声警告 beep
    for at, f0 in ((0.50, 880), (0.585, 1174)):
        k = int(0.055 * sr)
        t = np.arange(k) / sr
        sq = (np.sign(np.sin(2 * np.pi * f0 * t)) * 0.35
              + np.sin(2 * np.pi * f0 * t) * 0.35) * np.exp(-t / 0.05)
        add(sq.astype(np.float32), at, 0.55)

    # 0.9 盖章
    k = int(0.17 * sr)
    t = np.arange(k) / sr
    thud = np.sin(2 * np.pi * 78 * np.exp(-8 * t) * t) * np.exp(-t / 0.045)
    click = rng.normal(0, 1, k) * np.exp(-t / 0.008) * 0.6
    add((thud * 0.9 + click).astype(np.float32), 0.9, 0.85)

    peak = float(np.max(np.abs(buf))) or 1.0
    pcm = (buf / peak * 0.72 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ============================================================ 主流程

def render_clip(base_src: Path, out_mp4: Path, cfg: OutroConfig,
                work: Path | None = None) -> Path:
    work = work or Path(tempfile.mkdtemp(prefix="outro_"))
    work.mkdir(parents=True, exist_ok=True)

    last_png = work / "last.png"
    extract_last_frame(base_src, last_png)
    backdrop = build_backdrop(Image.open(last_png), cfg)
    lay = layout_of(cfg)

    frames_dir = work / "frames"
    frames_dir.mkdir(exist_ok=True)
    hold_frames = int(round(cfg.hold * FPS))
    total = FRAMES + hold_frames
    for f in range(total):
        # head：先定格完整页（用动画的终帧渲染），再从头演一遍
        # tail：演完定格（用终帧继续渲染，光标和红心还在动）
        if cfg.hold_at == "head":
            anim_f = (FRAMES - 1) if f < hold_frames else (f - hold_frames)
        else:
            anim_f = min(f, FRAMES - 1)
        # 闪烁/呼吸用真实时间 f，所以定格阶段画面仍然“活着”
        render_frame(backdrop, anim_f, cfg, lay, clock=f).save(frames_dir / f"{f:03d}.png")

    audio_wav = work / "click.wav"
    if cfg.audio:
        # 音效长度必须跟总时长一致，否则 -shortest 会把画面剪短
        lead = cfg.hold if cfg.hold_at == "head" else 0.0
        synth_audio(audio_wav, DURATION + cfg.hold, offset=lead)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-framerate", str(FPS), "-i", str(frames_dir / "%03d.png")]
    if cfg.audio:
        cmd += ["-i", str(audio_wav), "-c:a", "aac", "-b:a", "192k",
                "-ar", "48000", "-ac", "1", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-movflags", "+faststart", str(out_mp4)]
    subprocess.run(cmd, check=True)
    return out_mp4


def attach(main_video: Path, outro: Path, out: Path) -> None:
    lst = outro.parent / "concat.txt"
    lst.write_text(f"file '{main_video.resolve().as_posix()}'\n"
                   f"file '{outro.resolve().as_posix()}'\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="1.5s 终端报错欺诈流片尾组件")
    ap.add_argument("--base", help="取最后一帧的视频/图片")
    ap.add_argument("--attach", help="把片尾接在这个视频后面")
    ap.add_argument("--out", required=True)
    ap.add_argument("--warning", default=OutroConfig.warning_text)
    ap.add_argument("--cta", default=OutroConfig.cta_text)
    ap.add_argument("--log", default=OutroConfig.log_text)
    ap.add_argument("--brand", default=OutroConfig.brand_text)
    ap.add_argument("--status", default=OutroConfig.status_text)
    ap.add_argument("--highlight", default=OutroConfig.highlight)
    ap.add_argument("--hold-at", choices=("head", "tail"), default=OutroConfig.hold_at,
                    help="head=开头先定格完整页（默认）；tail=动画结束后定格")
    ap.add_argument("--hold", type=float, default=OutroConfig.hold,
                    help="终帧定格秒数（默认 0.5；给 0 就是原来的 1.5s）")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--work")
    args = ap.parse_args()

    cfg = OutroConfig(warning_text=args.warning, cta_text=args.cta,
                      log_text=args.log, brand_text=args.brand,
                      status_text=args.status, highlight=args.highlight,
                      hold=args.hold, hold_at=args.hold_at, audio=not args.no_audio)

    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="outro_"))

    if args.attach:
        main_video = Path(args.attach)
        clip = work / "outro.mp4"
        render_clip(main_video, clip, cfg, work)
        attach(main_video, clip, Path(args.out))
        print(f"[attach] {main_video.name} + 1.5s 片尾 -> {args.out}")
        return 0

    if not args.base:
        ap.error("要么给 --base，要么给 --attach")
    render_clip(Path(args.base), Path(args.out), cfg, work)
    total = FRAMES + int(round(cfg.hold * FPS))
    pos = "开头" if cfg.hold_at == "head" else "结尾"
    print(f"[done] {args.out}  {total} 帧 @ {FPS}fps  {DURATION + cfg.hold:.2f}s "
          f"(定格 {cfg.hold:.1f}s 在{pos})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
