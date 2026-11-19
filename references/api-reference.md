# API 参考 · 写场景时查这张表

> 只列**场景文件能用到**的公开接口。坐标系一律是**成片像素 / 1080×1920**，
> 时间单位一律**秒**，`t=0` 是这一场的开头。
> 完整实现见 `03-动画/layout.py`、`管线/scripts/motion.py`、`03-动画/scene_kit.py`。

---

## 0. 场景文件契约（`render_scene.py` 只认这两个名字）

```python
DURATION = 12.90                      # 必须：这一场多长（秒）
def frame(t: float) -> Image.Image:   # 必须：给任意 t，返回 1080×1920 的图
    ...
W, H = 1080, 1920                 # 可选，默认就是这个
```

- `DURATION` 要和 `layout.SCENE_SLOTS` 里这一场的时长一致（差太多会导致合成错位）。
- 必须是**纯函数**：同 `t` 必出同一帧，禁止 `random` / 当前时间 / 全局状态。
- 返回值给 `c.finish()`（mode 一般是 RGB 或 RGBA，`render_scene.py` 会按需转）。
- 没有 `draw()` 别名——旧文档写的 `def draw(t):` 跑不起来。

---

## 1. `layout.py` — 版式唯一真源

### 常量（随 `activate()` 重算，**只读**）

| 名字 | 类型 | 含义 |
|---|---|---|
| `W`, `H` | int | 画布尺寸，默认 1080×1920 |
| `SAFE` | dict | `{"top":140, "right":72, "bottom":460, "left":60}`，注意 `bottom` 是**下边距**，不是 y 坐标 |
| `CONTENT` | (l, t, r, b) | 内容区，默认 `(72, 400, 1008, 1290)` |
| `CONTENT_LEFT/TOP/RIGHT/BOTTOM` | int | 上面四个数拆开，方便直接用 |
| `TITLE_BAND` | (top, bottom) | 标题层允许区，corner 默认 `(254, 360)` |
| `SUBTITLE_BAND` | (top, bottom) | 字幕带，默认 `(1300, 1460)`，**禁区** |
| `PIP_CX/CY/R` | int | 圆头像圆心与半径（默认 840 / 1555 / 140） |
| `PIP` | (x0,y0,x1,y1) | 圆头像包围盒，默认 `(700,1415,980,1695)` |
| `PIP_W/PIP_H/PIP_RADIUS` | int | 直径 / 半径 |
| `PIP_BORDER/FEATHER/SHADOW/SHADOW_OFFSET/SHADOW_ALPHA` | | 白边 2px / 羽化 10 / 阴影模糊 22 / 偏移 (0,10) / alpha 120 |
| `HEAD_BOX/HEAD_CX/HEAD_CY` | int | 从源画幅裁头的方框与中心，默认 520 @ (570,838) |
| `PIP_ENTER/PIP_EXIT/PIP_POP` | float | 转场时长：缩角 0.70 / 回全屏 0.55 / 弹出 0.40 |
| `SYNC_LEAD` | float | 画面领先台词的秒数，默认 0.12 |
| `SCHEDULE`, `SCENE_SLOTS` | list | **单集数据**：分段状态、场次表 `(sid, stem, t0, t1, dur)` |
| `MODE` / `ACTIVE_PROFILE` | str | 当前模式 `corner` / `cut` |

### 函数

```python
L.available() -> list[str]                    # 已定参数的模式
L.activate(name: str) -> None                 # 切模式并重算全部常量；未定参数的模式抛 NotImplementedError
L.lead(t: float) -> float                     # == t + SYNC_LEAD，场景第一行用它
L.state_at(t: float) -> (state, progress)     # state ∈ full / pip / to_pip / to_full
L.pip_crop(progress) -> (x0,y0,x1,y1)         # 从人物整帧里裁哪块（0=整幅，1=头部方框）
L.pip_rect(progress) -> (x0,y0,x1,y1)         # 贴在画布哪里（0=满屏，1=圆头像包围盒）
L.pip_radius(progress) -> int                 # 圆角半径（0=直角，1=正圆）
L.pip_feather(progress) -> float              # 羽化量
L.pip_params(progress) -> (crop, rect, radius, feather)   # 一次拿齐；合成用这个
L.rect_hits_content(rect, pad=8) -> bool      # 验收：矩形有没有压到人物框
L.circle_hits(px, py, pad=6) -> bool          # 验收：某点是否落在圆头像里
```

**方向陷阱**：`state_at` 给的 `progress` 是"这段过渡已经走了多少"，
所以 `to_full` 要传 `1 - progress` 给 `pip_params()`（`compose_final.py` 已经这么做了）。

---

## 2. `motion.py` — 画布与缓动

### 画布

```python
Canvas(w=1080, h=1920, ss=2, bg=None, base=None)
```

`ss=2` 是 2 倍超采样（画完 `finish()` 缩回），文字边缘才干净；`base` 给定不透明底图时
内部用 **RGB** 画布（这样 `ImageDraw` 才真正做 alpha 混合）。

| 方法 | 签名要点 |
|---|---|
| `rect(box, fill=None, outline=None, width=1, opacity=1.0)` | `box=(x0,y0,x1,y1)` |
| `rounded_rect(box, r, fill=None, outline=None, width=1, corners=None, opacity=1.0)` | `r` 圆角 |
| `ellipse(box, fill=None, outline=None, width=1, opacity=1.0)` | |
| `polygon(pts, fill=None, outline=None, width=1, opacity=1.0)` | `pts=[(x,y), ...]` |
| `line(pts, fill, width=2, joint="curve", opacity=1.0)` | |
| `text(x, y, s, font_name="yh", size=64, fill=C.text, anchor="la", tracking=0, shadow=None, shadow_blur=0, shadow_offset=(0,8), stroke=0, stroke_fill=None, opacity=1.0)` | 返回 `(宽, 高)`；**y 是顶边** |
| `text_mixed(x, y, s, size=44, fill=C.text, ascii_font="bahn", cjk_font="yh_b", tracking=0, opacity=1.0, ascii_scale=1.0, cjk_scale=1.0)` | **y 是基线**；返回宽度 |
| `text_shadow(x, y, s, font_name, size, fill, anchor="la", tracking=0, blur=24, offset=(0,14), shadow_alpha=170)` | 先模糊阴影再画字 |
| `layer() -> (img, draw)` | 新建透明图层 |
| `composite(im, opacity=1.0)` / `paste(im, x, y, opacity=1.0)` | 叠图层（RGB 画布下只贴有内容的区域） |
| `_comp(layer, pos=(0,0))` | 底层混色；场景里需要手动混就调这个，**不要** `c.img.alpha_composite()` |
| `glow(box, color, radius=40, strength=200, rounded=40)` | 光晕 |
| `vignette(strength=90)` | 边缘压暗 |
| `finish() -> Image` | 缩回 1080×1920 |

字体名：`yh`（雅黑）/ `yh_b`（雅黑 Bold）/ `yh_l` / `bahn`（数字西文）/ `consola` / `consolab` /
`deng` / `deng_b` / `noto` / `noto_b`。**中文别给 `bahn`**——会自动回退到 `yh_b` 并打一次 WARN。

### 时间与缓动

```python
stage(t, start, dur, fn=ease_out_cubic) -> float   # 绝对时间 → 0..1 局部进度
alpha_in(t, start, dur=0.35) -> float
clamp(x, a=0.0, b=1.0)
lerp(a, b, p)
ease_out_cubic / ease_in_cubic / ease_in_out_cubic / ease_out_expo / ease_out_back(p, s=1.7)
spring(p, freq=3.0, damp=6.0)
vertical_gradient(w, h, top, bottom) -> Image      # RGBA
```

### 配色 `C`

`bg / bg_deep / card / card_solid / line / line_soft / text / text_dim / amber / danger / cold / red / white / black`
（都是 4 元组 RGBA）。

### 排字检查

```python
with motion.text_tracking() as boxes:   # 进出自动复位，异常也不留脏框
    mod.frame(t)
    # boxes = [{"t": 文本, "box": [x0,y0,x1,y1], "size": 字号, "a": 透明度}, ...]
```

---

## 3. `scene_kit.py` — 视觉语法（`import scene_kit as K`）

### 文案与开关

```python
K.TEXT                      # 文案表：{"s07_55cents": ("标题", "副标")} 或 "标题"
K.TITLE_MODE                # "mid" / "light" / "off"，来自环境变量 KOUBO_TITLE
K.title_for(key) -> (标题, 副标)
```

### 底层与标题层

```python
K.background(ss=2) -> Image              # 渐变底 + 网格 + 冷光（带缓存）
K.canvas(t=0.0, ss=2) -> Canvas          # 场景第一件事
K.scrim_top(height=None, strength=210)   # 顶部深色渐隐膜（带缓存）
K.scrim_box() -> (x0, y0, x1, y1)        # 薄膜覆盖区；①④ 验收会把它排除在「内容」外
K.scene_head(c, key, t, t_in=0.30, dur=0.50, scrim=True)
    # 标题层唯一入口。key 传场景主干，或直接传 ("标题", "副标") 临时覆盖
K.chapter(c, t, idx, label, y=None, t_in=0.10)
    # 章节角标；与 scene_head 二选一
```

### 文字层级

```python
K.headline(c, t, text, y=None, size=60, t_in=0.20, dur=0.55, color=None)   # 内容区大标题
K.label(c, t, text, y, size=34, color=None, t_in=0.0, x=X, tracking=2, alpha=1.0)
K.number(c, t, value, x, y, size, color=None, decimals=0, t_in=0.6, dur=1.30,
         bounce=1.35, prefix="", suffix="") -> float        # 返回最终宽度
K.rule(c, t, y, x0=X, x1=XN, t_in=0.0, dur=0.55, color=(127,166,201,80), width=2)
```

### 图形

```python
K.bar(c, t, x, y, w, h, frac, color, t_in=0.0, dur=0.8, bg_color=..., radius=None)
K.vbar(c, t, x, y_bottom, w, h_max, frac, color, t_in=0.0, dur=0.9)
K.arrow(c, t, p0, p1, color=None, width=5, head=20, t_in=0.0, dur=0.5)
K.pill(c, t, x, y, text, size=32, fg=None, bg=None, t_in=0.0, pad=22, h=56)
K.card(c, t, box, fill=None, stroke=None, radius=18, t_in=0.0, alpha=1.0)
K.cross(c, t, cx, cy, r, color=None, t_in=0.0, dur=0.45, width=8)
K.check(c, t, cx, cy, r, color=None, t_in=0.0, dur=0.45, width=8)
K.strike(c, t, x0, x1, y, color=None, t_in=0.0, dur=0.40, width=5)
K.shake(t, t0, amp=10, dur=0.45) -> (dx, dy)
K.dim(c, alpha=0.55)
K.letter_card(c, box, letter, sub="", t_in=0.0, alpha=1.0, color=None)
    # 首字母灰卡：查不到/没授权的人物图，用这个替身，别配错人
```

`X = L.CONTENT[0]`（内容左沿），`XN = L.W // 2`（左栏右界）。

---

## 4. `_paths.py` — 路径与场景发现（写脚本时用）

```python
import _paths
_paths.ensure_import_path()          # 找到 <工作区>/管线/scripts 并塞进 sys.path
_paths.HERE                          # 03-动画 目录
_paths.discover_scenes(scenes=None) -> list[Path]   # 只匹配 ^s\d{2}_.*\.py$（忽略大小写）
_paths.matches(path, keys) -> bool   # s07 / S07 / s07_xxx / scenes/s07_xxx.py 都认
_paths.resolve_scene(arg) -> Path
_paths.load_scene(path) -> module
_paths.scene_id(path) -> "s07"
```

---

## 5. `compose_final.py` 里可复用的两个函数

```python
CF.person_card(person, crop, dest, radius, feather) -> (layer, (x, y))
    # 从人物整帧裁一块 -> 贴成圆角卡片；头像 = crop 头部方框 + dest 边长 + radius 半边长
CF.ClipReader(path)   # 顺序读一个场景片段（30fps，无音频）
```

`size_options.py` 就是拿 `person_card` 出三档尺寸对比图的。

---

## 6. 最小可跑场景（复制就能用）

```python
# 03-动画/scenes/s01_hello.py
import layout as L
import scene_kit as K
from motion import C, stage

DURATION = 14.0


def frame(t: float):
    ts = L.lead(t)                                   # 画面领先 0.12s
    c = K.canvas(ts)
    K.scene_head(c, "s01_hello", ts)

    left, top, right, bottom = L.CONTENT
    a = stage(ts, 1.0, 0.6)
    if a > 0:
        K.card(c, ts, (left, top + 60, right, top + 420), t_in=1.0)
        c.text(left + 32, top + 100, "807", "bahn", 140, C.amber, opacity=a)
        c.text(left + 32, top + 300, "一笔表外附注，撑起两万亿估值", "yh", 36, C.text_dim,
               opacity=a)

    # 结尾别静止：低频呼吸也算动
    c.rect((left, bottom - 40, left + 200 + 80 * stage(ts, 2.0, 9.0), bottom - 24),
           fill=(79, 209, 197, 220))
    return c.finish()
```

配套：`TEXT["s01_hello"] = ("第一场在讲什么", "可选副标")` 要加到 `scene_kit.TEXT`，
再把这一场登记进 `layout.SCENE_SLOTS`（`("S01", "s01_hello", 起始秒, 结束秒, 14.0)`）。
