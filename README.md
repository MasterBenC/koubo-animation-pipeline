# 口播动画片生产线 · koubo-animation-pipeline

> 给一条真人出镜的口播视频，做成「人物缩成右下角圆头像 + 全幅动画讲清楚内容」的
> **1080×1920 竖屏**成片。不是一个提示词模板，是一套**能跑起来的生产工具链**：
> 代码、六道验收脚本、踩坑清单全在里面。

适用于 **DeepSeek Harness** / Claude Code / Codex 等支持 `~/.agents/skills` 约定的 Agent。

- **平台：Windows Only**（字体走系统字体目录；ffmpeg / Python 3.10+ / pillow / numpy）
- **画幅：仅竖屏 1080×1920**（横屏两组参数还是空的，选到会直接抛错）

---

## 这个 skill 解决什么问题

你录了一条口播，内容不错，但画面就是一个人对着镜头说话。
想加图表、加剖面图、加流程，让它像「财经拆解视频」而不是「网课录屏」。

难点从来不是「画一个动画」，而是：

1. **人物怎么缩**——缩到哪、多大、头有没有被切
2. **字幕放哪**——后期要烧字幕，画面得先给它让位
3. **十几场怎么统一**——不能看起来像十几个人做的
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
| 1 | 语音转写，拿到每句话的精确时间（词级） |
| 2 | 定剪点 → 粗剪 → timemap → 复转比对（≥0.95）→ 台词表 cues |
| 3 | 画面超分到 1080×1920 |
| 4 | 定版式：内容区 / 标题层 / 字幕带 / 圆头像 / 头部裁切 |
| 5 | 台词表拆成动画场景，逐场实现并逐场自检 |
| 6 | 批量渲染 + 与人物层合成 + `loudnorm` 到 −14 LUFS |
| 7 | 六道自动验收，全绿才出片（字幕最后单独出） |

交付：`1080×1920` 成片 mp4 + 对齐好的 `final.srt`。
**字幕不烧进画面**——你在剪映里自己烧，断句和位置更准。

---

## 四种版式模式

按素材选，选错等于重做：

| | 右下角画中画 | 人与动画互切 |
|---|---|---|
| **竖屏 9:16** | ✅ `portrait/corner`（唯一 ready） | `portrait/cut`（几何已定） |
| **横屏 16:9** | 待模板 | 待模板 |

**怎么选**（顺序问，任意一个指向互切就用互切）：

- 手在画面里比划 / 背景杂乱 / 图表数据占大头 → **互切**（信息优先）
- 胸像 + 背景干净 + 金句型内容 + 竖屏信息流 → **右下角**（陪伴优先）

切换只有一个入口：`set LAYOUT_PROFILE=portrait/cut`（Windows）或 `L.activate(...)`。
选到没定参数的模式会直接 `NotImplementedError`，不会静默出错。

---

## 四条设计原则（也是它跟别的 video skill 的区别）

### 1. 字幕绝不烧进画面

字幕由创作者手工烧。Agent 只交付对齐好时间轴的 SRT。
画面里任何一行台词都是「图形元素」（标题/数字/标签），不是字幕——
这样你烧上去的字不会跟它打架。

### 2. 节拍跟着台词走

动画不是按秒均摊的。**新元素出现的时刻 = 对应台词起点 − 0.15 秒**（代码里就是
`ts = L.lead(t)`，画面**提前** 0.12 s），任何超过 1.2 秒的画面静止都算缺陷。

实测教训：有一场戏在讲最狠的一句话时，画面静止了 6 秒。
这类问题肉眼看不出来，必须用 `audit_timing.py` 量。

### 3. 六道自动验收，不靠肉眼

| 检查 | 拦住什么 |
|---|---|
| `check_layout.py` | 内容越界 / 压到圆头像 / 进了字幕带 |
| `check_text.py` | 两行字叠在一起 |
| `audit_band.py` | 标题排到字幕带里 |
| `audit_canvas.py` | 只用了半边画布、下半屏空（宽 <80% / 下沿 <1150） |
| `audit_timing.py` | 动画比台词早/晚、结尾静止 |
| `audit_text_band.py` | **文字整体出界**（标题层顶出画布、副标压进字幕带） |

六道全绿才算做完。

### 4. 画面里的字只做标题层

这条是两轮返工换来的：先把画面里的字全删（结果"太单一"），再加回来——**只留标题层**：
每场一行标题 + 可选一句副标，压在 `layout.TITLE_BAND`（y 254–360），字幕带一个像素不碰。
入口只有一个：`K.scene_head()`；文案集中在 `scene_kit.TEXT` 字典。
标题不复述台词，只回答"这场在讲什么"；柱状图的比例要诚实（讲 90 倍就不能画成 3:1）。

---

## 里面有什么

```
koubo-animation-pipeline/
├── SKILL.md                  触发词 + 八条铁律 + 标题层规范 + 七个阶段 + 六道验收
├── meta.yaml                 技能市场元数据（中英双语，含平台/画幅边界）
├── install.py                一条命令装工具链 + 建新片子
├── references/
│   ├── cases-2026-11.md      真实成片的案件回灌（用户改了什么、为什么）
│   ├── pipeline.md           完整命令与参数
│   ├── schemas.md            cuts/segments/timemap/words/cues 的字段契约
│   ├── api-reference.md      layout / motion / scene_kit 的全部公开签名
│   ├── layout-rules.md       版式规则 / 节拍纪律 / 头部标定法
│   ├── modes.md              四种版式的选型判据
│   └── pitfalls.md           34 条真实踩过的坑
└── assets/pipeline/          全部可执行代码
    ├── scripts/              transcribe / build_edl / cut / build_cues / make_srt /
    │                         motion / render_scene / vision
    ├── 成片/_模板/03-动画/    layout.py、scene_kit.py、_paths.py、六道验收脚本
    ├── 组件/outro_terminal.py 可直接用的片尾组件
    └── 生产手册.md            一页流程索引（细则都在 references/）
```

代码是真的能跑通的（已用 `install.py` 装到临时工作区跑过全链路冒烟：
装工具链 → 写场景 → 六道验收 → 渲片段 → 剪片 → 出 cues/srt）。

### 附带的片尾组件

`outro_terminal.py` —— 「终端报错欺诈流」片尾：1.5 秒动画 + 0.5 秒首帧定格。
用它把「双击点赞」包在系统报错的假故障里，冷幽默但不油腻。

```bash
python 管线/组件/outro_terminal.py --attach 02-剪辑/05-成片.mp4 --out 06-带片尾.mp4
```

---

## 环境要求

- **Windows**（字体走 `%WINDIR%\Fonts`，用 Consolas / 微软雅黑 / Bahnschrift）
- Python 3.10+，`pillow` `numpy`；转写要 `faster-whisper`
- ffmpeg 6+（PATH 里能直接调，需要 `ffprobe`）

非 Windows / 精简版 Windows：把 `msyh.ttc`、`msyhbd.ttc`、`bahnschrift.ttf`、
`consola*.ttf` 放进一个目录，设 `KOUBO_FONT_DIR` 指向它。缺字体会明确报错并列出找过的路径。

可选环境变量：`LAYOUT_PROFILE` / `KOUBO_FONT_DIR(S)` / `KOUBO_TITLE` /
`KOUBO_ASR_MODELS` / `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL` / `VISION_CONFIG`。

---

## 已知限制

- 面向**单人出镜**的口播（多人对话没有做过）
- 仅竖屏 1080×1920；横屏参数未定
- 版式默认值来自一支财经片，换题材要重新标定头部裁切框（`references/layout-rules.md` 有方法）
- `measure_head.py` 在 OpenCV 5 上不可用（读不了 YuNet），头部标定用手动网格法
- 不做 BGM 自动配乐（留给后期）

---

## 版本

**0.4.1** · 第三条成片回灌（EP.05「英伟达 48 小时四连反转」）

- `check_layout.py` **重新支持场景自带的 `bg_frame(t)`**：照片底/双色底拿它做差，
  否则退回通用底会把整帧背景当成"内容"，19 场能全假失败一遍；缺 `bg_frame` 时脚本会
  打印 `[!] 本场缺模块级 def bg_frame(t)` 并说明修法
- `SKILL.md` 场景模板与铁律 3 都加上 `bg_frame(t)`；阶段 2 补「整段不剪」的最短路径
  （`timemap.json` 只写 `output_duration`、`cues.json` 记得复制到 `02-剪辑/`）
- 响度补「增益 + 限幅」这一版：源素材 TP > −3 dB 时线性增益会削波、`loudnorm` 动态模式
  稳定欠 0.5–0.7 dB；给出 `volume + alimiter(level=false, limit=0.80)` 的实测配方与复测命令
- 验收接线三条坑写进 `SKILL.md` 阶段 7 与 `pitfalls.md` 35–38：
  `bg_frame` 缺失 / `motion.text_tracking` 版本错位 / `audit_timing` 读 `02-剪辑/cues.json`
- 素材抓取两条坑（`pitfalls.md` 43–44）：Cloudflare 验证页会被截成"正常大小"的假截图；
  Playwright 截图超时多是字体加载，拦掉 `resource_type == "font"` 即可
- `references/cases-2026-11.md` 增 EP.05 案例：19 场 / 302.7 s 的工期基线、底序列排法、
  口播与来源不一致的三处处理、素材命中率

**0.4.0** · 评审整改（跑不通/会做错的问题全修）

- 去掉全部私人硬编码路径：`vision.py` 改读 `VISION_API_KEY`，ASR 模型目录走环境变量，
  `pos_options` / `size_options` 改成命令行参数
- 补齐幽灵脚本：新增 `cut.py`（按 segments 粗剪 + 写 timemap）、`build_cues.py`（words→cues），
  标题层收进 `scene_kit.scene_head`；删掉 `new_project.py` / `kit_clean` 这类只存在于文档里的名字
  （评审点名的 `layout.py` / `scene_kit.py` / `make_check_png.py` 仓库里本来就有，
  是文档写法和真契约不符，已改文档而不是重复造文件）
- 修相对路径：新增 `_paths.py` 统一「向上找 scripts」，`audit_*` / `check_*` / `compose_final`
  不再数 `parents[N]`；`render_scene.py` 自己把场景目录塞进 `sys.path`
- 阶段 2 补全链路：`build_edl → cut → transcribe(复转) → build_cues → make_srt`
- 阶段 5 示例改成真契约 `def frame(t) -> Image`，坐标全从 `layout` 推
- 音画同步方向改正：`SYNC_LEAD = 0.12` + `L.lead(t)`（画面**提前**），全局统一
- 响度改 `loudnorm=I=-14:TP=-1.0:LRA=11`，删掉 `volume=7.2dB` 硬编码
- 验收口径对齐脚本真判据（宽 ≥80%、下沿 ≥1150、文字框 x 72–1008 / y 140–1290），
  修掉「1200−1121=29px」的算术错误
- 全库统一「六道验收」；`meta.yaml` / `SKILL.md` 明确 **Windows Only / 竖屏 1080×1920**
- 脚本层：`make_srt` 的 ASR 纠错表外置到 `<项目>/01-asr/fixes.json`；`motion.TRACK`
  改成 `text_tracking()` 上下文管理器；字体加回退链与明确报错；场景发现统一
  `^s\d{2}_.*\.py$`（大小写不敏感）
- 新增 `references/schemas.md`、`references/api-reference.md`
- `生产手册.md` 从 21 KB 降级为一页索引；`pitfalls.md` 去重并统一
  `Path.write_text(..., encoding="utf-8")`

**0.3.0** · 两条真实成片回灌（EP.03 / EP.04）

- 新增「画面里的字只做标题层」规范（两轮返工定稿：全删 → 嫌单一 → 只留标题 + 副标）
- 新增第六道验收 `audit_text_band.py`：文字整体出界检查
- SKILL.md 新增铁律 7「破坏性操作先复述确认」（误删 0.94 GB 的教训）、铁律 8「字是导航不是字幕」
- 版式表补实测值：头部裁切 `box=980 @ (590,932)`、画面领先 0.12s、底要四种轮换

**0.2.0** · 四模式版式

- `layout.py` 改成按 `(方向, 模式)` 取配置；默认值与原版**逐像素一致**（已做回归）
- 新增 `portrait/cut`（竖屏互切）几何：内容区从 890 高扩到 1070
- `check_layout.py` 支持无画中画模式（自动跳过圆检查）
- 新增 `references/modes.md`：选型判据 + 拍摄自检 + 各模式参数

**0.1.0** · 首个公开版

- 七个阶段全流程 / 自动验收脚本（后扩到六道） / 圆头像画中画 + 全屏双向转场 / 片尾组件

---

## License

MIT
