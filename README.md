# 口播动画片生产线 · koubo-animation-pipeline

> 给一条真人出镜的口播视频，做成「人物缩成右下角圆头像 + 全幅动画讲清楚内容」的 9:16 竖屏成片。
> 不是一个提示词模板，是一套**能跑起来的生产工具链**：代码、验收脚本、踩坑清单全在里面。

适用于 **DeepSeek Harness** / Claude Code / Codex 等支持 `~/.agents/skills` 约定的 Agent。

---

## 这个 skill 解决什么问题

你录了一条口播，内容不错，但画面就是一个人对着镜头说话。
想加图表、加剖面图、加流程，让它像「财经拆解视频」而不是「网课录屏」。

难点从来不是「画一个动画」，而是：

1. **人物怎么缩**——缩到哪、多大、头有没有被切
2. **字幕放哪**——后期要烧字幕，画面得先给它让位
3. **16 个场景怎么统一**——不能看起来像 16 个人做的
4. **动画怎么对上台词**——最容易翻车的一环
5. **怎么知道做完了没**——不能靠肉眼一遍遍看

这个 skill 把这五件事**固化成了参数、脚本和验收命令**。

---

## 装法

### 方式一：克隆到 skills 目录（推荐）

```bash
git clone https://github.com/MasterBenC/koubo-animation-pipeline.git \
  ~/.agents/skills/koubo-animation-pipeline
```

Windows：

```powershell
git clone https://github.com/MasterBenC/koubo-animation-pipeline.git "$env:USERPROFILE\.agents\skills\koubo-animation-pipeline"
```

重开一个会话，skill 列表里就会出现 `koubo-animation-pipeline`。

### 方式二：手动

下载仓库 zip，解压到 `~/.agents/skills/koubo-animation-pipeline/`
（保证这个目录下直接就能看到 `SKILL.md`）。

### 装完先跑一句，确认工具链没坏

```bash
python ~/.agents/skills/koubo-animation-pipeline/install.py \
  --root "<你的工作区>" --name 测试片 --title "自测"
```

它会建出 `管线/` 全套工具并打印下一步。

---

## 怎么用

装好之后，直接对 Agent 说人话：

> 这条口播帮我做成片：`D:\素材\口播-0321.mp4`

Agent 会按 SKILL.md 的七个阶段走：

| 阶段 | 干什么 |
|---|---|
| 1 | 语音转写，拿到每句话的精确时间 |
| 2 | 按静音定剪点，剪完复转比对相似度（≥0.95） |
| 3 | 画面超分到 1080×1920 |
| 4 | 定版式：内容区 / 字幕带 / 圆头像 / 头部裁切 |
| 5 | 台词表拆成若干动画场景，逐场实现 |
| 6 | 批量渲染 + 与人物层合成 + 响度归一到 -14 LUFS |
| 7 | 五道自动验收，全绿才出片 |

交付：`1080×1920` 成片 mp4 + 对齐好的 `final.srt`。
**字幕不烧进画面**——你在剪映里自己烧，断句和位置更准。

---

## 四种版式模式

按素材选，选错等于重做：

| | 右下角画中画 | 人与动画互切 |
|---|---|---|
| **竖屏 9:16** | ✅ `portrait/corner` | `portrait/cut`（几何已定） |
| **横屏 16:9** | 待模板 | 待模板 |

**怎么选**（顺序问，任意一个指向互切就用互切）：

- 手在画面里比划 / 背景杂乱 / 图表数据占大头 → **互切**（信息优先）
- 胸像 + 背景干净 + 金句型内容 + 竖屏信息流 → **右下角**（陪伴优先）

切换：`set LAYOUT_PROFILE=portrait/cut`（Windows）或 `export LAYOUT_PROFILE=...`。
选到没定的模式会直接报错并列出可用项，不会静默出错。

---

## 三条设计原则（也是它跟别的视频 skill 的区别）

### 1. 字幕绝不烧进画面

字幕由创作者手工烧。Agent 只交付对齐好时间轴的 SRT。
画面里任何一行台词都是「图形元素」（标题/数字/标签），不是字幕——
这样你烧上去的字不会跟它打架。

### 2. 节拍跟着台词走

动画不是按秒均摊的。**新元素出现的时刻 = 对应台词起点 − 0.15 秒**，
任何超过 1.2 秒的画面静止都算缺陷。

实测教训：有一场戏在讲最狠的一句话时，画面静止了 6 秒。
这类问题肉眼看不出来，必须用 `audit_timing.py` 量。

### 3. 五道自动验收，不靠肉眼

| 检查 | 拦住什么 |
|---|---|
| `check_layout.py` | 内容越界 / 压到圆头像 / 进了字幕带 |
| `check_text.py` | 两行字叠在一起 |
| `audit_band.py` | 标题排到字幕带里 |
| `audit_canvas.py` | 只用了半边画布、下半屏空 |
| `audit_timing.py` | 动画比台词早/晚、结尾静止 |

五道全绿才算做完。

---

## 里面有什么

```
koubo-animation-pipeline/
├── SKILL.md                  触发词 + 六条铁律 + 七个阶段
├── meta.yaml                 技能市场元数据（中英双语）
├── install.py                一条命令装工具链 + 建新片子
├── references/
│   ├── pipeline.md           完整命令与参数
│   ├── layout-rules.md       版式规则 / 节拍纪律 / 头部标定法
│   └── pitfalls.md           20 条真实踩过的坑
└── assets/pipeline/          全部可执行代码
    ├── scripts/              motion.py（动画底层）、render_scene.py、transcribe.py…
    ├── 成片/_模板/03-动画/    layout.py、scene_kit.py、五道验收脚本
    ├── 组件/outro_terminal.py 可直接用的片尾组件
    └── 生产手册.md            人读的完整手册
```

代码是**真的能跑**的：全部来自一支已发布的 264 秒成片（16 个动画场景）。

### 附带的片尾组件

`outro_terminal.py` —— 「终端报错欺诈流」片尾：1.5 秒动画 + 0.5 秒首帧定格。
用它把「双击点赞」包在系统报错的假故障里，冷幽默但不油腻。

```bash
python 管线/组件/outro_terminal.py --attach 05-成片.mp4 --out 06-带片尾.mp4
```

---

## 环境要求

- **Windows**（字体走 `%WINDIR%\Fonts`，用 Consolas / 微软雅黑）
- Python 3.10+，`pillow` `numpy`；转写要 `faster-whisper`
- ffmpeg 6+（PATH 里能直接调）

macOS / Linux 需要改 `motion.py` 的 `FONT_DIR` 和字体文件名，其余逻辑通用。

---

## 已知限制

- 面向**单人出镜**的口播（多人对话没有做过）
- 版式默认值来自一支财经片，换题材要重新标定头部裁切框（`references/layout-rules.md` 有方法）
- `measure_head.py` 在 OpenCV 5 上不可用（读不了 YuNet），头部标定用手动网格法
- 不做 BGM 自动配乐（留给后期）

---

## 版本

**0.2.0** · 四模式版式

- `layout.py` 改成按 `(方向, 模式)` 取配置；默认值与原版**逐像素一致**（已做回归）
- 新增 `portrait/cut`（竖屏互切）几何：内容区从 890 高扩到 1070
- `check_layout.py` 支持无画中画模式（自动跳过圆检查）
- 新增 `references/modes.md`：选型判据 + 拍摄自检 + 各模式参数
- 横屏两组参数待模板

**0.1.0** · 首个公开版

- 七个阶段全流程
- 五道自动验收
- 圆头像画中画 + 全屏双向转场
- 终端报错欺诈流片尾组件

---

## License

MIT
