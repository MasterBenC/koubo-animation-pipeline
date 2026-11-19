# 完整流程与命令

> SKILL.md 给的是骨架，这里是可以直接抄的命令和参数。
> 所有路径都相对**项目根**（`<工作区>/管线/成片/<项目>`）和**工作区**（`<工作区>`），
> 没有私人绝对路径。

---

## 环境

Windows + Python 3.10+ + ffmpeg（含 ffprobe）+ Pillow + numpy；ASR 另需 `faster-whisper`。

```powershell
# 只需要两件事：脚本能跑、临时目录够大
$env:TEMP="<工作区>\work\tmp"; $env:TMP=$env:TEMP
```

**不需要设 PYTHONPATH。** `03-动画/_paths.py` 会向上找 `管线/scripts`，
`render_scene.py` 会自己把场景目录塞进 `sys.path`。旧文档里那种
`$env:PYTHONPATH="C:\Users\xxx\Desktop\某项目\管线\scripts"` 那种写法是历史遗留，换台机器就废。

可选环境变量：

| 变量 | 用途 |
|---|---|
| `LAYOUT_PROFILE` | 版式模式，默认 `portrait/corner` |
| `KOUBO_FONT_DIR` / `KOUBO_FONT_DIRS` | 自定义字体目录（非 Windows / 精简版系统） |
| `KOUBO_TITLE` | 标题层开关 `mid` / `light` / `off` |
| `KOUBO_ASR_MODELS` | faster-whisper 模型目录 |
| `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL` | `vision.py` 看图的接口 |
| `VISION_CONFIG` | 上面三个的 KEY=VALUE 文件 |

**Windows 上的三个必踩坑先说：**

1. `Get-Content` 在 PowerShell 5.1 默认按 ANSI 读，中文乱码不代表文件坏了。
   要确认编码用 `python -c "print(open(p,encoding='utf-8').read()[:200])"`。
2. `[System.IO.File]::WriteAllText` 的相对路径按**进程 CWD** 解析，不是当前目录。一律绝对路径。
3. 写文本统一 `Path(...).write_text(text, encoding="utf-8")`（Python 侧），
   PowerShell 侧要无 BOM 就显式 `UTF8Encoding($false)`。
   **中间件 JSON 一律 UTF-8 无 BOM**；`final.srt` 用 `utf-8-sig`（剪映/播放器对 BOM 更宽容）。

---

## 阶段 1 · ASR

```powershell
python "<工作区>\管线\scripts\transcribe.py" "<项目>\01-原片\raw.mp4" -o "<项目>\01-asr" `
  --model large-v3 --lang zh --threads 16
```

| 参数 | 说明 |
|---|---|
| `-o` | 输出目录 |
| `--model` | `large-v3`（默认）。要快可用 `medium` |
| `--lang` | `zh` |
| `--threads` | CPU 线程，默认 16 |
| `--beam` | 默认 5 |
| `--no-vad` | 关掉 VAD |
| `--model-root` | 模型目录；不给就用 faster-whisper 默认缓存或 `KOUBO_ASR_MODELS` |

产物：

| 文件 | 用途 |
|---|---|
| `逐字稿.md` | 带时间码的全文，**主要给人和 AI 读** |
| `words.json` | **词级**时间（`segments[].words[].start/end`），做精确卡点 |
| `raw.srt` | 句子级字幕（源片时间轴，别直接交付） |
| `audio.wav` | 抽出来的 16k 单声道音轨 |

> `silences.json` 不存在：静音/剪点是在 `cuts.json` 里人工或半自动定的，
> `build_edl.py` 只负责把 `deletes[]` 算成 keep 段。别在文档里引用不存在的产物。

---

## 阶段 2 · 剪辑决策 → 粗剪 → 时间映射 → 台词表

```powershell
# ① cuts.json -> segments.json + timemap.json（--out 给目录；给 xxx.json 也行）
python "<工作区>\管线\scripts\build_edl.py" "<项目>\02-剪辑\cuts.json" -o "<项目>\02-剪辑" --min-keep 0.12

# ② 按 keep 段重掐（重编码，不用 -c copy），顺手写 timemap
python "<工作区>\管线\scripts\cut.py" --input "<项目>\01-原片\raw.mp4" `
  --segments "<项目>\02-剪辑\segments.json" `
  --out "<项目>\02-剪辑\02-粗剪.mp4" --timemap "<项目>\02-剪辑\timemap.json"

# ③ 复转比对：相似度 <0.95 就要回头看剪点（参考值 264 秒片删 34 秒 = 0.968）
python "<工作区>\管线\scripts\transcribe.py" "<项目>\02-剪辑\02-粗剪.mp4" -o "<项目>\02-剪辑\asr_verify"

# ④ 台词表（成片时间轴）
python "<工作区>\管线\scripts\build_cues.py" "<项目>\02-剪辑\asr_verify\words.json" `
  -o "<项目>\02-剪辑\cues.json" --dump
```

`cuts.json` 是人工/半自动定的删除区间（`{"source_duration": 300.0, "deletes": [{"start": 12.4, "end": 15.1}, ...]}`），
`--min-keep` 是保留段的最短长度。

**字幕**（只在验收全绿后出最终版）：

```powershell
python "<工作区>\管线\scripts\make_srt.py" --proj "<项目>" -o "<项目>\final.srt" --max-chars 18
# 等价写法：直接指 words.json（剪过片就用 asr_verify 那份）
python "<工作区>\管线\scripts\make_srt.py" "<项目>\02-剪辑\asr_verify\words.json" -o "<项目>\final.srt"
```

纠错表在 `<项目>\01-asr\fixes.json`（`{"错词": "正词"}`），没有就不纠错。
**不要把某集的错别字表写进脚本**——那会静默篡改下一支片子的台词。

**整段不剪的片子**（EP.05：302.73 s / 语音占比 99% / 无口误段）跳过 ①②③：

```powershell
# 原片直接超分成人物母版；timemap.json 只留时长（compose_final 只读这一项）
# 内容就一行：{"output_duration": 302.73, "note": "无剪辑，原片整段使用"}

# cues 直接用原片的 words.json 生成到 文案/，再复制一份到 02-剪辑/ 给 audit_timing
python "<工作区>\管线\scripts\build_cues.py" "<项目>\01-asr\words.json" -o "<项目>\文案\cues.json" --dump
Copy-Item "<项目>\文案\cues.json" "<项目>\02-剪辑\cues.json"
```

省掉的不只是两条命令，还有一次全片重编码（画质损失）和一次复转。

字段契约见 `references/schemas.md`。

---

## 阶段 3 · 画面提升

```powershell
ffmpeg -hide_banner -y -i "<项目>\02-剪辑\02-粗剪.mp4" `
  -vf "scale=1080:1920:flags=lanczos,unsharp=5:5:0.5:5:5:0" `
  -c:v libx264 -crf 16 -preset medium -pix_fmt yuv420p -c:a copy "<项目>\02-剪辑\03-超分.mp4"
```

锐化参数是 A/B/C 实测选出来的（`unsharp=5:5:0.5`）。**不要上强锐化**，人脸会脏。

---

## 阶段 4 · 版式

**只有一个入口**：改 `<项目>/03-动画/layout.py` 里 `PROFILES[模式]` 那一块，切模式用
`LAYOUT_PROFILE` 环境变量或 `L.activate("portrait/cut")`。

```python
# PROFILES["portrait/corner"] 里这几个键
safe=dict(top=140, right=72, bottom=460, left=60),
content=(72, 400, 1008, 1290),
title=(254, 360),                 # 标题层允许区
subtitle_band=(1300, 1460),
pip=dict(cx=840, cy=1555, r=140, ...),
head=dict(box=520, cx=570, cy=838),
```

不要直接给模块级 `SAFE` / `CONTENT` / `PIP_CX` 赋值——`activate()` 会在切换时重算它们，
手改会被覆盖。`SCHEDULE` / `SCENE_SLOTS` 是**单集数据**，装新片时整块替换。

出确认图：

```powershell
python "<项目>\03-动画\make_check_png.py" <成片帧.png> "构图验收.png"
```

图上会标出安全区、内容区、字幕带、圆头像的实际位置和边距。

参数类微调（圆的位置/大小）一次出 3 档真图给用户选：

```powershell
python 03-动画\pos_options.py  --video "<项目>\02-剪辑\04-合成.mp4" --at 60 --out 预览\圆心三档.png
python 03-动画\size_options.py --person "<项目>\02-剪辑\03-超分.mp4" --bg "<项目>\02-剪辑\04-合成.mp4" `
  --person-at 147.5 --bg-at 55 --out 预览\圆尺寸三档.png
```

---

## 阶段 5 · 场景

目录：`<项目>/03-动画/scenes/sNN_名字.py`。每个文件导出 `DURATION` 和 `frame(t)`
（**没有 `draw()` 别名**，`render_scene.py` 只调 `frame`）：

```python
import layout as L
import scene_kit as K
from motion import C, stage

DURATION = 12.90


def frame(t: float):
    ts = L.lead(t)                       # 画面领先 0.12s（正向）
    c = K.canvas(ts)
    K.scene_head(c, "s07_55cents", ts)    # 标题层，落区由 L.TITLE_BAND 管
    ...
    return c.finish()
```

公共件（`layout` / `motion` / `scene_kit` 的完整签名见 `references/api-reference.md`）：

| 函数 | 用途 |
|---|---|
| `K.canvas(t)` | 统一背景（深色网格 + 冷光） |
| `K.scene_head(c, key, t)` | 标题层（标题 + 副标），文案取 `TEXT[key]` |
| `K.chapter(c, t, "01", "利润表 · 底层结构")` | 左上角章节标（y 默认取 layout） |
| `K.headline(c, t, "标题", ...)` | 大标题（内容区用，不是标题层） |
| `K.number(c, t, 807, x, y, size, C.amber)` | 数字滚动，返回最终宽度 |
| `K.rule / bar / vbar / arrow / pill / card / cross / check / strike / shake / dim` | 图形原语 |
| `K.scrim_top(h)` | 顶部深色渐隐薄膜 |

写完立刻自检（一场几秒，别攒着）：

```powershell
cd "<项目>\03-动画"
python check_layout.py s07 --step 0.5
python check_text.py s07 --fps 10
python audit_band.py s07
python audit_canvas.py s07
python audit_text_band.py s07
```

场景筛选一律**大小写不敏感**：`s07` / `S07` / `s07_55cents` / `scenes/s07_55cents.py` 都行。

---

## 阶段 6 · 渲染 + 合成

```powershell
cd "<项目>\03-动画"

# 批量渲染（参数是场景编号或文件名主干；大小写不敏感）
python build_clips.py --force --jobs 4 --crf 17
python build_clips.py --force --jobs 4 --crf 17 s07 s11 s12 s16     # 只渲某几场

# 合成（片段 + 人物 → 成片）
python compose_final.py --out "..\02-剪辑\04-合成.mp4"
python compose_final.py --from 72.20 --to 85.10 --out preview\sample.mp4   # 只出片段

# 响度：-14 LUFS / TP ≤ -1.0 dBTP
ffmpeg -hide_banner -y -i "..\02-剪辑\04-合成.mp4" `
  -af "loudnorm=I=-14:TP=-1.0:LRA=11" `
  -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "..\02-剪辑\05-成片.mp4"
```

**响度不要写死增益。** `volume=7.2dB` 只是当年那条 −19.2 LUFS 素材的差值；
换素材会偏离 −14，源素材本来就削波时还会更糟。要么一把 `loudnorm`，
要么先 `ffmpeg -af ebur128 -f null -` 量出来再补。要更准时用两遍法
（第一遍 `loudnorm=...:print_format=json` 拿 `measured_I/TP/LRA`，第二遍套回去）。

**素材峰值高时（源 TP > −3 dB）改用「增益 + 限幅」**（EP.05 实测）：

```powershell
ffmpeg -hide_banner -y -i "..\02-剪辑\04-合成.mp4" `
  -af "volume=6.75dB,alimiter=limit=0.80:attack=4:release=80:level=false" `
  -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "..\02-剪辑\05-成片.mp4"

# 收尾必测（I / Peak / LRA 三个数都看）
ffmpeg -hide_banner -i "..\02-剪辑\05-成片.mp4" -af "loudnorm=I=-14:TP=-1.0:print_format=json" -f null -
```

- `level=false` 不能省（默认会自己抬电平，实测顶到 +0.24 dBTP）；
- `limit` 按编码后真峰值倒推，0.891 实测仍 −0.83 dBTP，0.80 才稳；
- `loudnorm` 单独用在这类口播上会稳定欠 0.5–0.7 dB，别为了追 −14.0 反复调 `I=`。

**速度参考**：16 场 / 264 秒素材，片段约 6~10 分钟（4 并发）；合成约 13~23 分钟。
EP.05 实测（19 场 / 302.7 s，5 并发）：片段 454 s、合成 817 s。


---

## 阶段 7 · 六道验收

```powershell
cd "<项目>\03-动画"

python check_layout.py s01 s02 --step 0.5   # ①
python check_text.py --fps 10               # ②
python audit_band.py                        # ③
python audit_canvas.py                      # ④
python audit_timing.py                      # ⑤
python audit_text_band.py                   # ⑥
```

| 脚本 | 参数 | 判据（脚本里写死的才是真数） |
|---|---|---|
| `check_layout.py` | `--step` 采样间隔、`--margin` 圆外扩容差、`--save` 存违规帧 | 圆侵入 0px；字幕带 <300px；安全区外只允许飞出镜头 |
| `check_text.py` | `--fps`、`--ratio 0.35`、`--min-px 900` | 无重叠（重叠面积 ≥ 小字框 35% 才报） |
| `audit_band.py` | 场景（`s12` / `S12`） | 字幕带 y 1300–1460 内无**文字** |
| `audit_canvas.py` | 场景 | 宽 ≥80%（对 936）、下沿 ≥1150 |
| `audit_timing.py` | 场景、`--thresh`（**变化像素个数**，默认 900）、`--fps` | 事件贴台词、无 >1.2s 死区 |
| `audit_text_band.py` | 场景、`--fps` | 文字框全在 x 72–1008 / y 140–1290 |

③ 与 ⑥ 的分工：③ 只查字幕带、逐场报压带像素；⑥ 查四条边（上沿 140 / 下沿 1290 / 左右 72–1008）。
两道都留着——③ 定位快，⑥ 抓标题层顶边。

---

## 片尾

```powershell
python "<工作区>\管线\组件\outro_terminal.py" --attach "<项目>\02-剪辑\05-成片.mp4" --out "<项目>\06-带片尾.mp4"
```

参数：`--warning` / `--cta` / `--log` / `--brand` / `--status` / `--highlight` /
`--hold`（定格秒数，默认 0.5）/ `--hold-at`（head/tail）/ `--no-audio`。
