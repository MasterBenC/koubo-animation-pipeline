# 完整流程与命令

> SKILL.md 给的是骨架，这里是可以直接抄的命令和参数。

---

## 环境

Windows + Python 3.11+ + ffmpeg 8.x + Pillow + numpy。

```powershell
# 每次开终端先设（路径按实际改）
$env:PYTHONPATH="<工作区>\管线\scripts"
$env:TEMP="<工作区>\work\tmp"; $env:TMP=$env:TEMP
```

依赖：`pillow` `numpy` `faster-whisper`（ASR）`opencv-python`（可选，见 pitfalls）。

**Windows 上的三个必踩坑先说：**

1. `Get-Content` 在 PowerShell 5.1 默认按 ANSI 读，中文乱码不代表文件坏了。
   要确认编码用 `python -c "open(p,encoding='utf-8').read()"`。
2. `[System.IO.File]::WriteAllText` 的相对路径按**进程 CWD** 解析，不是当前目录。一律绝对路径。
3. `Set-Content -Encoding UTF8` 会写 BOM，ffmpeg 的 concat 列表带 BOM 会直接报错。
   写文本用 `[System.IO.File]::WriteAllText($f,$t,(New-Object System.Text.UTF8Encoding($false)))`。

---

## 阶段 1 · ASR

```powershell
python "<工作区>\管线\scripts\transcribe.py" "<原片.mp4>" -o "<项目>\01-asr" `
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

产物：

| 文件 | 用途 |
|---|---|
| `逐字稿.md` | 带时间码的全文，**主要给人和 AI 读** |
| `words.json` | 词级时间，做精确卡点 |
| `raw.srt` | 句子级字幕 |
| `silences.json` | 静音检测，做剪辑用 |
| `audio.wav` | 抽出来的音轨 |

---

## 阶段 2 · 剪辑决策

```powershell
python "<工作区>\管线\scripts\build_edl.py" `
  --cuts "<项目>\02-剪辑\cuts.json" `
  --out  "<项目>\02-剪辑\segments.json" `
  --min-keep 0.12
```

`cuts.json` 是人工/半自动定的删除区间。`--min-keep` 是保留段的最短长度。

剪完**必须复转比对**：

```powershell
python "<工作区>\管线\scripts\transcribe.py" "<项目>\02-剪辑\02-粗剪.mp4" -o "<项目>\02-剪辑\check-asr"
```

比对两次转录的相似度，**低于 0.95 就回头看剪点**（参考值：264 秒片、删 34 秒、相似度 0.968）。

然后生成 `timemap.json`：原片时间 ↔ 成片时间。后面所有时间轴都靠它换算。

---

## 阶段 3 · 画面提升

```bash
ffmpeg -i 02-粗剪.mp4 -vf "scale=1080:1920:flags=lanczos,unsharp=5:5:0.5:5:5:0" \
  -c:v libx264 -crf 16 -preset medium -pix_fmt yuv420p -c:a copy 03-超分.mp4
```

锐化参数是 A/B/C 实测选出来的（`unsharp=5:5:0.5`）。**不要上强锐化**，人脸会脏。

---

## 阶段 4 · 版式

改 `<项目>/03-动画/layout.py`。四个必改项：

```python
SAFE = dict(top=140, right=72, bottom=460, left=60)
CONTENT = (72, 400, 1008, 1290)
SUBTITLE_BAND = (1300, 1460)
PIP_CX, PIP_CY, PIP_R = 840, 1555, 140     # 圆头像
HEAD_BOX = 520                             # 从源画幅裁头的框
HEAD_CX, HEAD_CY = 570, 838
```

出确认图：

```powershell
python "<项目>\03-动画\make_check_png.py" <成片帧.png> "构图验收.png"
```

图上会标出安全区、内容区、字幕带、圆头像的实际位置和边距。

---

## 阶段 5 · 场景

目录：`<项目>/03-动画/scenes/sNN_名字.py`。每个文件导出：

```python
DURATION = 12.90          # 秒
def frame(t): return draw(t)
```

可用的公共件（`scene_kit.py`）：

| 函数 | 用途 |
|---|---|
| `K.canvas(t)` | 统一背景（深色网格 + 光） |
| `K.chapter(c, t, "01", "利润表 · 底层结构", 220)` | 左上角章节标 |
| `K.headline(c, t, "标题", 282, 54, t_in=0.15)` | 大标题，带入场 |
| `K.rule(c, t, 382, t_in=0.55)` | 分隔线 |
| `K.number(c, t, 807, X, y, 156, C.amber, t_in=..., dur=1.15)` | 数字滚动 |
| `K.card(...)` `K.strike(...)` `K.cross(...)` | 卡片 / 划掉 / 打叉 |

动画原语（`motion.py`）：`stage(t, t0, dur, ease)`、`ease_out_cubic` 等缓动、
`C` 配色表、`Canvas`（`text / rect / rounded_rect / line / ellipse / polygon`）。

写完立刻自检：

```powershell
python check_layout.py scenes\sNN_xxx.py --step 0.5
python audit_band.py sNN
```

---

## 阶段 6 · 渲染 + 合成

```powershell
cd "<项目>\03-动画"

# 批量渲染（参数是场景 ID，不是文件名；没有 --only）
python build_clips.py --force --jobs 4 --crf 17
python build_clips.py --force --jobs 4 --crf 17 S07 S11 S12 S16   # 只渲某几场

# 合成（片段 + 人物 → 成片）
python compose_final.py --out "..\02-剪辑\04-合成.mp4"
python compose_final.py --from 72.20 --to 85.10 --out preview\sample.mp4   # 只出片段

# 响度
ffmpeg -y -i "..\02-剪辑\04-合成.mp4" `
  -af "volume=7.2dB,alimiter=limit=0.841:attack=4:release=55:level=false" `
  -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "..\02-剪辑\05-成片.mp4"
```

**响度**：目标 `-14 LUFS / TP ≤ -1.0 dBTP`。`volume` 必须在 `alimiter` **之前**。
实测：源 -19.2 LUFS / TP +0.4（已削波）→ 提 7.2dB 再限制 → -14.2 / -1.4。

**速度参考**：16 场 / 264 秒素材，片段约 6 分钟（4 并发）；合成约 13.6 分钟。

---

## 阶段 7 · 五道验收

```powershell
cd "<项目>\03-动画"
$files = Get-ChildItem scenes\*.py | Where-Object { $_.Name -ne "demo_ledger.py" } | ForEach-Object { "scenes\" + $_.Name }

python check_layout.py @files --step 0.5     # ①
python check_text.py  @files --fps 10        # ②
python audit_band.py                         # ③
python audit_canvas.py                       # ④
python audit_timing.py                       # ⑤
```

| 脚本 | 参数 | 判据 |
|---|---|---|
| `check_layout.py` | `--step` 采样间隔、`--margin` 圆外扩容差、`--save` 存违规帧 | 圆侵入 0px、字幕带 0px |
| `check_text.py` | `--fps` 采样帧率、`--ratio`、`--min-px` | 无文字重叠 |
| `audit_band.py` | 场景名前缀（如 `s12`） | 字幕带内无文字 |
| `audit_canvas.py` | 无 | 宽占 ≥85%、下沿 ≥1200 |
| `audit_timing.py` | 场景前缀、`--thresh`、`--fps` | 事件贴台词、无 >1.2s 死区 |

---

## 字幕（只出文件，不烧）

```powershell
python "<工作区>\管线\scripts\make_srt.py" --proj "<项目>" -o "<项目>\final.srt" --max-chars 18
```

`--max-chars` 控制每条最多几个字。产物是对齐成片时间轴的 SRT，
**不进 ffmpeg，不烧进画面**。

---

## 片尾

```powershell
python "<工作区>\管线\组件\outro_terminal.py" --attach "<项目>\02-剪辑\05-成片.mp4" --out "<项目>\06-带片尾.mp4"
```

参数：`--warning` / `--cta` / `--log` / `--brand` / `--status` / `--highlight` /
`--hold`（定格秒数，默认 0.5）/ `--hold-at`（head/tail）/ `--no-audio`。
