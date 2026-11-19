---
name: koubo-animation-pipeline
description: |
  口播视频配动画的完整生产线。给一条真人出镜的口播视频，做出「人物缩成右下角圆头像 + 全幅动画讲清楚内容」的 1080×1920 竖屏成片，含剪辑、动画、合成、响度、六道自动验收。
  平台：Windows Only（实测基准）。脚本是纯 Python + ffmpeg，**不依赖 PowerShell**；Windows 特化的只有字体默认目录，非 Windows 设 KOUBO_FONT_DIR 指向同名字体目录即可。
  触发：给口播配动画 / 口播剪辑 / 口播视频做成片 / 竖屏知识视频 / 9:16 讲解片 / 口播加图表 / 财经口播 / 「这条口播帮我做成片」「给视频配动画」「口播太单调了」。
  也适用于：一条口播要拆成多个动画场景、要统一的版式规范、要有自动验收不靠肉眼。
  不适用：横屏长视频、无人出镜的纯剪辑、多人对话、只做一段动效素材。
  English: Turn a talking-head video into a 9:16 (1080x1920) explainer with a circular face-cam PiP and full-width animated scenes — cutting, layout, per-scene animation, compositing, loudness, and six automated QA passes. Windows only (tested baseline): pure Python + ffmpeg, no PowerShell dependency; the only OS-specific bit is the default font directory — set KOUBO_FONT_DIR on other systems.
  Trigger: talking-head to animation, explainer video, 9:16 knowledge video, add motion graphics to a talking head, voiceover video editing.
---

# 口播动画片生产线

把一条真人出镜的口播视频，做成「人物缩成右下角圆头像 + 全幅动画讲清楚内容」的竖屏成片。

> **平台：Windows Only（实测基准）。** 版式与默认参数是按 Windows + 1080×1920 竖屏标定的。
> 依赖只有 `ffmpeg` / `ffprobe` / Python 3.10+ / `pillow` / `numpy`，脚本是纯 Python 调 ffmpeg，
> **不依赖 PowerShell**（文档里 `set X=Y` 这类写法只是 Windows 用户习惯，换 `export X=Y` 同效）。
> Windows 特化的只有字体默认目录 `%WINDIR%\Fonts`（微软雅黑 / Bahnschrift / Consolas）；
> 非 Windows 设 `KOUBO_FONT_DIR`（或 `KOUBO_FONT_DIRS`，`;` 分隔）指向放了同名字体的目录即可，
> 代码还会自动找 `~/.local/share/fonts`。整片流程未在非 Windows 上实测，按「未验证」对待。

这套流程已经在三条成片上跑通过（264 s / 326.1 s / 336.6 s，16–21 个动画场景，−14 LUFS）：
第一条定版式，后两条是案例回灌——**用户真实改过什么、我们因此改了什么，全写在
`references/cases-2026-11.md`**。开工前先读它，再读 `references/pitfalls.md`。
**不要重新发明版式和验收方式**，照这个走。

---

## 第 0 步：装工具链（没做这步，后面全跑不了）

```bash
python <这个 skill 的目录>/install.py --root "<用户的工作区>" --name <项目名> --title "<片子标题>"
```

它会在工作区里建：

```
<工作区>/管线/
├── scripts/          ASR、剪辑、渲染、看片、字幕
├── 组件/             片尾组件
├── 生产手册.md        人看的流程索引（细则都在本 skill 的 references/）
└── 成片/<项目名>/
    ├── BRIEF.md      立项卡
    ├── 01-原片/ 01-asr/ 02-剪辑/
    └── 03-动画/      版式、场景工具箱、渲染、六道验收
```

装完先确认这一步能过：

```bash
cd "<工作区>/管线/成片/<项目名>/03-动画"
python -c "import layout as L; print(L.PIP, L.CONTENT, L.TITLE_BAND)"
```

> 脚本之间不靠 `PYTHONPATH` 串：`03-动画/_paths.py` 会向上找到 `管线/scripts`，
> `render_scene.py` 会把场景目录自己塞进 `sys.path`。所以别在文档里教人设 `PYTHONPATH`
> 到某个私人绝对路径——换台机器就废。

---

## 八条铁律

### 1. 字幕一律不烧 ★ 最高优先级

字幕由**用户手工在剪映里烧**，因为只有他知道每句断在哪、停多久、多大字。
我们只交付对齐好时间轴的 `final.srt`。

- 成片 mp4 里不许出现任何字幕像素
- ffmpeg 禁止用 `subtitles=` / `ass=` / `drawtext=` 画台词
- 动画里的字是**画面元素**（标题/数字/标签），不是字幕，**也不要拿它顶替字幕**——
  用户烧上去的字会盖在这些位置，两层字打架
- 交付时必须写「字幕未烧，final.srt 供后期使用」

这条比「画面好看」优先。

### 2. 版式只有一个真源
所有坐标来自 `03-动画/layout.py`。**任何场景都不许写死坐标**，改版式只改这一个文件
（模式参数改 `PROFILES` 里对应那一块）。

### 3. 节拍跟着台词走，不按秒均摊
新元素出现的时刻 = 对应台词起点 **− 0.12 秒**（视觉略领先，读起来最舒服）。全库只有这一个数，
不要再写成 `0.00~0.15` 的区间。**绝不晚于台词。** 任何超过 1.2 秒的画面静止都是缺陷。

代码口径只有一种写法（别搞反）：

```python
def bg_frame(t):                 # ★ 背景必须提成模块级函数，验收脚本靠它做差
    return K.canvas(t)           # 照片底/双色底就在这一行里自己拼（paste + K.dim）


def frame(t):
    c = bg_frame(t)
    ts = L.lead(t)      # == t + L.SYNC_LEAD(0.12)，画面提前 0.12s
```

`t -= 0.12` 是让画面**延后**，方向正好反了；旧版本文档写成那样是错的。

**`bg_frame(t)` 不是可选项。** `check_layout.py` 拿「只有背景的同一帧」做差来判断内容越界；
场景里若把背景在 `frame()` 内部现拼（不放 `bg_frame`），它只能退回通用底，照片底/双色底会整帧都是差异，
一场就能假报几十万像素越界（EP.05 19 场全假失败一遍才发现）。缺 `bg_frame` 时脚本现在会打印
`[!] 本场缺模块级 def bg_frame(t)`，照着提示把那行提出来即可。

### 4. 每写完一场立刻自检，不要攒到最后
`check_layout` / `audit_band` / `audit_text_band` 一场只跑几秒，攒到最后一起改会互相干扰。

### 5. 不要先写动画再对时间
先把台词表（`cues.json`）打印出来，把每个视觉元素挂到某一句上，再写代码。
第一版反着做，返工最狠的就是这里。

### 6. 参数类决策给图不给话
用户说「再大一点」「往下一点」时，**一次渲染 3 档真图**给他选
（`pos_options.py` / `size_options.py` 就是干这个的），不要用文字描述让他脑补。
这个片子光圆头像位置就来回改了 4 轮，改成「一次给 3 档」后一轮就定了。

### 7. 破坏性操作先复述再动手 ★
用户说「把 EP03 都删掉」时，先回一句「我要删的是 A，不是 B，对吗？」
这条是用 500 个文件 / 0.94 GB 永久删除换来的：用户的意思是「把视频里的字删掉」，
我删了整个项目目录，回收站没进。

### 8. 画面里的字是导航，不是字幕
一屏最多「1 个主信息 + 1 条副信息」；但一屏一个字没有，观众会觉得这集没做完。
两头都被用户否过：先嫌字多、全删之后又说「太单一」。落地方案见下面「画面里的字」一节。

---

## 画面里的字：只做标题层

竖屏口播最容易做错的两头：做成满屏解释文字（像 PPT），或者一个字都不放（像半成品）。
用户的最终口径是**只保留标题层**——每场一行标题、可选的副标，回答"这场在讲什么"：

| 项 | 值 |
|---|---|
| 结构 | 一行标题（微软雅黑 Bold 44 / 米白）+ 一句副标（25 / 冷灰），副标可省 |
| 落区 | 只在 `layout.TITLE_BAND` 里（corner 模式 y 254–360）；内容区 400–1290、**字幕带一像素不碰** |
| 可读性 | 顶部压一层深色渐隐薄膜（`K.scrim_top()`）+ 标题垫 55% 黑影；照片底上也要读得清 |
| 装饰 | 左侧 5px 琥珀竖条，入场时从上往下长出来 |
| 入场 | 每场 `t_in≈0.3 s`、0.5 s 淡入；副标入场轻微上浮 |
| 实现 | 只有一个入口 `K.scene_head(c, key, t)`；文案在场景目录的 `TEXT` 字典里，一行一场 |
| 开关 | 环境变量 `KOUBO_TITLE=mid / light / off`（标题+副标 / 只标题 / 回纯图），方便给用户看两版 |

三条纪律：

1. **标题不复述台词**，只回答"这场在讲什么"；标题里出现数字，必须和画面、字幕同一个口径。
2. **不写日期行/来源行/时间码**：竖屏没地方，而且用户后期要烧字幕，底部一律让出来。
3. **比例要诚实**：用柱状图讲"涨了 90 倍"，柱子就不能画成 3:1——要么真比例，
   要么别画比例尺（只给数字标签）。EP.03 这张图被 vision 一眼抓出来过。

配套验收：`audit_text_band.py`（第六道，见阶段 7）。

---

## 七个阶段

### 阶段 1 · ASR
```bash
python "<工作区>/管线/scripts/transcribe.py" "<原片>" -o "<项目>/01-asr" --model large-v3 --lang zh
```
产物：`逐字稿.md`（带时间码）、`words.json`（**词级** start/end）、`raw.srt`、`audio.wav`。

**ASR 不是为了出字幕，是为了知道每句话在第几秒。** 后面所有节拍都从这张表推。

### 阶段 2 · 剪辑决策 → 粗剪 → 时间映射 → 台词表

四步一条链，少一步后面必断（`final.srt` 要的就是这条链的产物）：

```bash
# ① 定剪点：cuts.json -> segments.json + timemap.json
python "<工作区>/管线/scripts/build_edl.py" "<项目>/02-剪辑/cuts.json" -o "<项目>/02-剪辑"

# ② 粗剪：按 keep 段重掐，顺手写 timemap（源时间 <-> 成片时间）
python "<工作区>/管线/scripts/cut.py" --input "<项目>/01-原片/raw.mp4" \
    --segments "<项目>/02-剪辑/segments.json" \
    --out "<项目>/02-剪辑/02-粗剪.mp4" \
    --timemap "<项目>/02-剪辑/timemap.json"

# ③ 复转比对（相似度 <0.95 就要回头看剪点，参考值 0.968）
python "<工作区>/管线/scripts/transcribe.py" "<项目>/02-剪辑/02-粗剪.mp4" \
    -o "<项目>/02-剪辑/asr_verify"

# ④ 台词表（成片时间轴）：场景挂节拍 + audit_timing 都读它
python "<工作区>/管线/scripts/build_cues.py" "<项目>/02-剪辑/asr_verify/words.json" \
    -o "<项目>/02-剪辑/cues.json" --dump
```

`final.srt` 也在这一步之后随时可出（阶段 7 验收全绿再出最终版）：

```bash
python "<工作区>/管线/scripts/make_srt.py" --proj "<项目>" -o "<项目>/final.srt" --max-chars 18
```

> **整段不剪的片子**（口播 99% 有语音、没有口误段，EP.05 就是这种）不要硬走 ①②③：
> 直接 `01-原片/raw.mp4` → `03-超分.mp4`，`timemap.json` 只写
> `{"output_duration": <原片时长>, "note": "无剪辑，原片整段使用"}`（`compose_final.py` 只读这一项），
> `cues.json` 用 `01-asr/words.json` 直接生成，**再复制一份到 `02-剪辑/cues.json`** 给 `audit_timing`。

> 剪过片就一定用**复转的那份** `asr_verify/words.json` 做字幕和 cues；
> 用原片那份会整体错位，而且不报错。字段定义见 `references/schemas.md`。

### 阶段 3 · 画面提升
```
scale=1080:1920:flags=lanczos,unsharp=5:5:0.5:5:5:0
```
强锐化会让人脸变脏。先出 A/B/C 三档对比给用户选。

### 阶段 4 · 定版式（决定后面所有事）

**先定模式**——四种，按素材选，选错等于重做：

| | 右下角画中画 | 人与动画互切 |
|---|---|---|
| 竖屏 9:16 | `portrait/corner` ✅ | `portrait/cut`（几何已定，状态机待实现） |
| 横屏 16:9 | `landscape/corner` 待模板 | `landscape/cut` 待模板 |

判据（顺序问，任意一个指向互切就用互切）：
手在画面里比划 → 互切；背景乱 → 互切；图表数据占大头 → 互切；
胸像 + 背景干净 + 金句型 + 竖屏信息流 → 右下角。
完整判据和拍摄自检见 `references/modes.md`。

**切模式只有一个合法入口**（`layout.py` 里 `PROFILES` + `activate()`）：

```bash
set LAYOUT_PROFILE=portrait/cut          # Windows，进程级
```
```python
import layout as L
L.activate("portrait/cut")               # 代码里切
```

不要直接给模块级 `SAFE` / `CONTENT` / `PIP_CX` 赋值——`activate()` 会在切换时重算它们，
手改会被下一次 activate 覆盖。

改 `03-动画/layout.py` 里**对应模式的那一块**：

| 区域 | 默认值 | 说明 |
|---|---|---|
| 内容区 | x 72–1008，y 400–1290 | 动画主体整个在这里 |
| 标题层 | y 254–360（`TITLE_BAND`） | 只放标题 + 副标 |
| 字幕带 | y 1300–1460 | **禁区，一个像素都不许进**（图形也不行） |
| 圆头像 | 直径 280，圆心 (840,1555) | 右距 100、下距 345 |
| 头部裁切 | 默认 520×520 中心 (570,838) | 从源画幅里裁头；**实测过 980 @ (590,932)**，见下 |
| 画面领先 | `SYNC_LEAD = 0.12` | 场景里 `ts = L.lead(t)`，画面略**早于**台词 |
| 场次表 | `SCHEDULE` / `SCENE_SLOTS` | **单集数据**，装新片时整块替换 |

**换人换片子必须重新标定头部裁切框**，而且别信默认值：EP.03 的机位实测是
`box=980 @ (590,932)`，比默认 520×520 大了一倍，照默认裁会把肩膀切掉；也别信单帧测量
（人说话会左右挪 100+ 像素）。手动网格标定法见 `references/layout-rules.md`。

**底的序列先排，再填内容。** 同一套大字体系，但背景四种底轮换（实拍 / 聚光黑底 / 双色章节 /
点阵航线），连续两场不许同一种——一条 5 分半的片子全场一个底，观众 90 秒就疲劳。
EP.04 的排法见 `references/cases-2026-11.md`。

改完出图给用户确认：
```bash
python 03-动画/make_check_png.py <成片帧.png> 构图验收.png
```

> 细节见 `references/layout-rules.md`。

### 阶段 5 · 写场景

每个场景一个文件：`scenes/sNN_名字.py`，**只要求 `DURATION` 和 `frame(t)`**
（`render_scene.py` 强制这个契约，没有 `draw()` 这种别名）：

```python
# scenes/s07_55cents.py
import layout as L
import scene_kit as K
from motion import C, stage

DURATION = 14.5                              # ① 这一场多长


def bg_frame(t: float):                      # ② 纯背景（验收脚本拿它做差，不许省）
    return K.canvas(t)


def frame(t: float):                         # ③ 这一帧画什么
    c = bg_frame(t)
    ts = L.lead(t)                           #    == t + 0.12，方向是 +
    K.scene_head(c, "s07_55cents", ts)       #    标题层落区由 L.TITLE_BAND 管
    left, top, right, bottom = L.CONTENT     #    坐标一律从 L 推，别写死数字
    a = stage(ts, 0.8, 0.6)
    if a > 0:
        c.text(left, top + 60, "5 毛 5", "bahn", 120, C.amber, opacity=a)
    return c.finish()
```

完整可跑范例与全部函数签名见 `references/api-reference.md`（§6 最小可跑场景）。

常用公共件（全部签名见 `references/api-reference.md`）：

| 从哪里 | 有什么 |
|---|---|
| `scene_kit.py` | `canvas / scene_head / chapter / headline / label / number / rule / bar / vbar / arrow / pill / card / cross / check / strike / shake / dim / scrim_top` + 文案表 `TEXT` |
| `motion.py` | `Canvas`（`text / text_mixed / rect / rounded_rect / line / ellipse / polygon / glow / vignette / paste / _comp / finish`）、`stage / ease_* / spring / clamp / lerp / C`、`text_tracking()` |

**先列台词表再挂元素**（铁律 5）。每写完一场立刻跑单场版验收（命令同阶段 7，多传一个场景号）：
`check_layout.py s07 --step 0.5` → `check_text.py s07 --fps 10` → `audit_band.py s07` →
`audit_canvas.py` → `audit_text_band.py s07`。⑤ `audit_timing` 留到整条时间轴齐了再跑
（它要把 `cues.json` 和场次表对起来）。

### 阶段 6 · 渲染 + 合成

```bash
cd 03-动画
python build_clips.py --force --jobs 4 --crf 17        # 16 场约 6~10 分钟
python compose_final.py --out "../02-剪辑/04-合成.mp4"  # 264 秒约 14 分钟

# 响度：目标 -14 LUFS / TP ≤ -1.0 dBTP
ffmpeg -hide_banner -y -i "../02-剪辑/04-合成.mp4" \
  -af "loudnorm=I=-14:TP=-1.0:LRA=11" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "../02-剪辑/05-成片.mp4"
```

**不要写死增益**（`volume=7.2dB` 只是某条 −19.2 LUFS 素材的差值，换素材会偏离甚至削波）。

- 普通素材：上面那行 `loudnorm` 一把过；要更准时先 `-af ebur128 -f null -` 量出 I/Peak 再套两遍法
  （`measured_*` 从第一遍 JSON 里抄）。
- **源 TP > −3 dB 的高峰值素材 `loudnorm` 会翻车**（动态模式实测稳定欠 0.5–0.7 dB，−14.6 ~ −14.9），
  改用增益 + 限幅：`-af "volume=6.75dB,alimiter=limit=0.80:attack=4:release=80:level=false"`。
  `level=false` 不能省（默认 `true` 会把电平抬回去，实测顶到 +0.24 dBTP）；`limit=0.80`
  （−1.94 dBFS 采样峰值）给 AAC 后的真峰值留余量（设 0.891 时成片 TPK 仍是 −0.83）。
- 收尾一律复测：`-af "loudnorm=I=-14:TP=-1.0:print_format=json" -f null -`。

实测数据与两遍法细节见 `references/pipeline.md` 阶段 6、`references/pitfalls.md` 39–42。

### 阶段 7 · 六道验收（一道都不能省）

```bash
cd 03-动画
python check_layout.py s01 s02 --step 0.5   # ①越界 / 压圆 / 进字幕带
python check_text.py --fps 10               # ②文字重叠
python audit_band.py                        # ③文字进字幕带（逐字精确）
python audit_canvas.py                      # ④画布利用率（宽 ≥80%、下沿 ≥1150）
python audit_timing.py                      # ⑤节拍 vs 台词
python audit_text_band.py                   # ⑥文字整体出界
```

| 检查 | 判据（以脚本为准） | 不通过的典型症状 |
|---|---|---|
| ① `check_layout` | 圆侵入 0px、字幕带 <300px、安全区外仅允许飞出镜头 | 内容压头像、字被字幕盖 |
| ② `check_text` | 重叠面积 < 小字框 35%，或 <900px² | 两行字叠一起 |
| ③ `audit_band` | 字幕带（y 1300–1460）内无**文字** | 标题排到 y1300 以下 |
| ④ `audit_canvas` | 宽 ≥80%（对 936）、下沿 ≥1150 | 只用半边画布、下半屏空 |
| ⑤ `audit_timing` | 事件贴台词、无 >1.2s 死区 | 画面自己走、结尾静止 |
| ⑥ `audit_text_band` | 文字框全在 x 72–1008 / y 140–1290 | 副标顶出右边界、标题压进字幕带 |

三道边界检查的分工，别搞混：

- ① 查**像素**（含图形、色块、卡片）对圆头像/字幕带/安全区；
- ③ 只查**文字**对字幕带，逐场报压带像素数，定位最快；
- ⑥ 查**文字**对四条边（上沿 140、下沿 1290、左右 72–1008）。③ 是 ⑥ 的子集，
  保留两道是因为 ③ 的报错更可读、⑥ 会连标题层顶边一起抓。

**⑤ 最容易漏，也最影响观感。** 前四道全绿但片子「不对劲」，八成是 ⑤。
`--thresh` 的单位是**变化像素个数**（不是帧、不是秒）：默认 900 看大动作，
`--thresh 60` 连轻动作和死区一起看。

两个会直接报错退出的坑（不是判据问题，是接线问题）：

- `audit_timing.py` 读 **`02-剪辑/cues.json`**，不是 `文案/cues.json`。没复制就
  `FileNotFoundError`，看起来像脚本坏了。
- `audit_text_band.py` 依赖 `motion.text_tracking()`。工作区里若用着旧版
  `管线/scripts/motion.py`（没有这个上下文管理器），会报
  `AttributeError: module 'motion' has no attribute 'text_tracking'`——把 skill 里的
  `assets/pipeline/scripts/motion.py` 覆盖过去即可（旧版备份成 `motion.py.bak_<集名>`）。

---

## 什么时候读哪个 reference

| 文件 | 什么时候读 |
|---|---|
| `references/cases-2026-11.md` | **开工前读**。两条真实成片：用户改了什么、为什么、实测参数 |
| `references/pipeline.md` | 要完整命令、参数、目录约定时 |
| `references/schemas.md` | 写/读 `cuts.json` `segments.json` `timemap.json` `cues.json` 时（字段是硬契约） |
| `references/api-reference.md` | 写场景时查函数签名（`layout` / `motion` / `scene_kit`） |
| `references/layout-rules.md` | 定版式、写场景、调节拍时（填充原则、节拍纪律、头部标定） |
| `references/modes.md` | **定模式时读**。四种版式的选型判据、拍摄自检、各模式参数 |
| `references/pitfalls.md` | **开工前读一遍**。真实踩过的坑，能省一整天 |

---

## 交付清单

| 文件 | 说明 |
|---|---|
| `02-剪辑/05-成片.mp4` | 成片，1080×1920 / 30fps / −14 LUFS |
| `06-带片尾.mp4` | 挂了片尾组件的版本（可选，只在用户要片尾时出） |
| `final.srt` | 字幕时间轴，**绝不烧进画面** |
| `QA.md` | 验收记录：时长、响度、六道检查结果 |
| `EDL.md` | 剪辑决策记录（cuts.json 的人读版） |
| `预览/*.png` | 构图验收图、分镜联系表、标题层一览 |
| 标题表 | 场景目录里的 `TEXT` 字典（一行一场），改字只改这里 |

---

## 片尾组件（可选）

`<工作区>/管线/组件/outro_terminal.py` —— 「终端报错欺诈流」片尾，
1.5 秒动画 + 0.5 秒首帧定格 = 2.0 秒（首帧=尾帧，让人读得完）。

```bash
python 管线/组件/outro_terminal.py --attach "02-剪辑/05-成片.mp4" --out "06-带片尾.mp4"
```

---

## 已知失效项 / 平台限制

- **Windows Only（实测基准）**：脚本是纯 Python + ffmpeg，不依赖 PowerShell；唯一 OS 特化的是
  字体默认目录（`%WINDIR%\Fonts`）。非 Windows 要设 `KOUBO_FONT_DIR` / `KOUBO_FONT_DIRS`
  指向放了 `msyh.ttc` / `msyhbd.ttc` / `bahnschrift.ttf` / `consola*.ttf` 的目录（代码也会找
  `~/.local/share/fonts`）。缺字体会**明确报错**并列出找过的路径（不会静默出方块字）。
  整片流程只在 Windows 上实测过。
- **仅竖屏 1080×1920**：`portrait/corner` 是唯一 `status=ready` 的版式；
  `portrait/cut` 只有几何、没有状态机；横屏两组参数还是空的（`activate()` 会直接抛
  `NotImplementedError`，不会静默出错）。
- `measure_head.py`（OpenCV 5 读不了 YuNet，且 cv2 在中文路径下打不开文件）——
  头部标定用手动网格法，见 `references/layout-rules.md`。
- `vision.py` 需要环境变量 `VISION_API_KEY`（或 `OPENAI_API_KEY`），可选
  `VISION_BASE_URL` / `VISION_MODEL`；没设直接报错退出。
