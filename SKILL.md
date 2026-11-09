---
name: koubo-animation-pipeline
description: |
  口播视频配动画的完整生产线。给一条真人出镜的口播视频，做出「人物缩成右下角圆头像 + 全幅动画讲清楚内容」的 9:16 竖屏成片，含剪辑、动画、合成、响度、五道自动验收。
  触发：给口播配动画 / 口播剪辑 / 口播视频做成片 / 竖屏知识视频 / 9:16 讲解片 / 口播加图表 / 财经口播 / 「这条口播帮我做成片」「给视频配动画」「口播太单调了」。
  也适用于：一条口播要拆成多个动画场景、要统一的版式规范、要有自动验收不靠肉眼。
  English: Turn a talking-head video into a 9:16 explainer with a circular face-cam PiP and full-width animated scenes — cutting, layout, per-scene animation, compositing, loudness, and five automated QA passes.
  Trigger: talking-head to animation, explainer video, 9:16 knowledge video, add motion graphics to a talking head, voiceover video editing.
---

# 口播动画片生产线

把一条真人出镜的口播视频，做成「人物缩成右下角圆头像 + 全幅动画讲清楚内容」的竖屏成片。

这套流程已经在一条 264 秒的成片上完整跑通过（16 个动画场景、5 道自动验收、-14 LUFS）。
**不要重新发明版式和验收方式**，照这个走。

---

## 第 0 步：装工具链（没做这步，后面全跑不了）

```bash
python <这个 skill 的目录>/install.py --root "<用户的工作区>" --name <项目名> --title "<片子标题>"
```

它会在工作区里建：

```
<工作区>/管线/
├── scripts/          ASR、渲染、看片
├── 组件/             片尾组件
├── 生产手册.md        人看的完整手册
└── 成片/<项目名>/
    ├── BRIEF.md      立项卡
    ├── 01-原片/ 01-asr/ 02-剪辑/
    └── 03-动画/      版式、场景工具箱、渲染、五道验收
```

装完先确认这一步能过：

```bash
cd "<工作区>/管线/成片/<项目名>/03-动画"
python -c "import layout as L; print(L.PIP)"
```

---

## 六条铁律

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
所有坐标来自 `03-动画/layout.py`。**任何场景都不许写死坐标**，改版式只改这一个文件。

### 3. 节拍跟着台词走，不按秒均摊
新元素出现的时刻 = 对应台词起点 − 0.00~0.15 秒（视觉略领先）。**绝不晚于台词。**
任何超过 1.2 秒的画面静止都是缺陷。

### 4. 每写完一场立刻自检，不要攒到最后
`check_layout` / `audit_band` 一次只跑几秒，攒到最后一起改会互相干扰。

### 5. 不要先写动画再对时间
先把台词表（`cues.json`）打印出来，把每个视觉元素挂到某一句上，再写代码。
第一版反着做，返工最狠的就是这里。

### 6. 参数类决策给图不给话
用户说「再大一点」「往下一点」时，**一次渲染 3 档真图**给他选，
不要用文字描述让他脑补。这个片子光圆头像位置就来回改了 4 轮，
改成「一次给 3 档」后一轮就定了。

---

## 七个阶段

### 阶段 1 · ASR
```bash
python "<工作区>/管线/scripts/transcribe.py" "<原片>" -o "<项目>/01-asr" --model large-v3 --lang zh
```
产物：`逐字稿.md`（带时间码）、`words.json`（词级）、`raw.srt`。

**ASR 不是为了出字幕，是为了知道每句话在第几秒。** 后面所有节拍都从这张表推。

### 阶段 2 · 剪辑决策
```bash
python "<工作区>/管线/scripts/build_edl.py" --cuts "<项目>/02-剪辑/cuts.json" --out "<项目>/02-剪辑/segments.json"
```
剪完**必须重新转录比对相似度**，低于 0.95 就要回头看剪点。
然后生成 `timemap.json`（原片时间 ↔ 成片时间），这是后面所有时间的换算基准。

### 阶段 3 · 画面提升
```
scale=1080:1920:flags=lanczos,unsharp=5:5:0.5:5:5:0
```
强锐化会让人脸变脏。先出 A/B/C 三档对比给用户选。

### 阶段 4 · 定版式（决定后面所有事）
改 `03-动画/layout.py`：

| 区域 | 默认值 | 说明 |
|---|---|---|
| 内容区 | x 72–1008，y 400–1290 | 动画主体整个在这里 |
| 字幕带 | y 1300–1460 | **禁区，一个像素都不许进** |
| 圆头像 | 直径 280，圆心 (840,1555) | 右距 100、下距 345 |
| 头部裁切 | 520×520，中心 (570,838) | 从源画幅里裁头 |

**换人换片子必须重新标定头部裁切框。** 别信单帧测量——人说话会左右挪 100+ 像素。
做法：抽 6–8 帧 → 缩到 540×960 叠 120px 网格 → 拼联系表 → 肉眼读头的范围 →
取能装下所有时刻的最小框 → 再放大 4%。

改完出图给用户确认：
```bash
python 03-动画/make_check_png.py <成片帧.png> 构图验收.png
```

> 细节见 `references/layout-rules.md`。

### 阶段 5 · 写场景
每个场景一个文件：`scenes/sNN_名字.py`，导出 `DURATION` 和 `frame(t)`。

```python
def draw(t):
    c = K.canvas(t)
    K.chapter(c, t, "01", "利润表 · 底层结构", 220)
    K.headline(c, t, "每赚 1 块钱，5 毛 5 交出去", 282, 54, t_in=0.15)
    coin(c, t); bar(c, t); vendors(c, t)
    return c.finish()
```

**先列台词表再挂元素**（铁律 5）。每写完一场立刻：
```bash
python check_layout.py scenes/sNN_xxx.py --step 0.5
python audit_band.py sNN
```

### 阶段 6 · 渲染 + 合成
```bash
python 03-动画/build_clips.py --force --jobs 4 --crf 17        # 16 场约 6 分钟
python 03-动画/compose_final.py --out "02-剪辑/04-合成.mp4"    # 264 秒约 14 分钟
ffmpeg -i 02-剪辑/04-合成.mp4 -af "volume=7.2dB,alimiter=limit=0.841:attack=4:release=55:level=false" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart 02-剪辑/05-成片.mp4
```

响度标准 **-14 LUFS / TP ≤ -1.0 dBTP**。`volume` 必须在 `alimiter` 之前，顺序不能换。

### 阶段 7 · 五道验收（一道都不能省）
```bash
cd 03-动画
python check_layout.py @files --step 0.5   # ①越界 / 压圆 / 进字幕带
python check_text.py  @files --fps 10      # ②文字重叠
python audit_band.py                       # ③文字进字幕带
python audit_canvas.py                     # ④画布利用率（宽 ≥85%、下沿 ≥1200）
python audit_timing.py                     # ⑤节拍 vs 台词
```

| 检查 | 判据 | 不通过的典型症状 |
|---|---|---|
| ① | 圆侵入 0px、字幕带 0px | 内容压头像、字被字幕盖 |
| ② | 无重叠 | 两行字叠一起 |
| ③ | 字幕带内无文字 | 标题排到 y1300 以下 |
| ④ | 宽 ≥85%、下沿 ≥1200 | 只用半边画布、下半屏空 |
| ⑤ | 事件贴台词、无 >1.2s 死区 | 画面自己走、结尾静止 |

**⑤ 最容易漏，也最影响观感。** 前四道全绿但片子「不对劲」，八成是 ⑤。

---

## 什么时候读哪个 reference

| 文件 | 什么时候读 |
|---|---|
| `references/pipeline.md` | 要完整命令、参数、目录约定时 |
| `references/layout-rules.md` | 定版式、写场景、调节拍时（填充原则、节拍纪律） |
| `references/pitfalls.md` | **开工前读一遍**。15 条真实踩过的坑，能省一整天 |

---

## 交付清单

| 文件 | 说明 |
|---|---|
| `05-成片.mp4` | 成片，1080×1920 / 30fps / -14 LUFS |
| `final.srt` | 字幕时间轴，**绝不烧进画面** |
| `QA.md` | 验收记录：时长、响度、五道检查结果 |
| `EDL.md` | 剪辑决策记录 |
| `预览/*.png` | 构图验收图、分镜联系表 |

---

## 片尾组件（可选）

`<工作区>/管线/组件/outro_terminal.py` —— 「终端报错欺诈流」片尾，
1.5 秒动画 + 0.5 秒首帧定格 = 2.0 秒（首帧=尾帧，让人读得完）。

```bash
python 管线/组件/outro_terminal.py --attach "02-剪辑/05-成片.mp4" --out "06-带片尾.mp4"
```

---

## 已知失效项

- `measure_head.py`（OpenCV 5 读不了 YuNet，且 cv2 在中文路径下打不开文件）——
  头部标定用手动网格法，见 `references/layout-rules.md`
- 所有脚本面向 Windows（字体取 `%WINDIR%\Fonts`）。换 macOS/Linux 要改
  `motion.py` 的 `FONT_DIR` 和字体文件名。
