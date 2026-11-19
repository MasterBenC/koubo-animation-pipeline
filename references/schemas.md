# 中间件 JSON 契约（跨阶段数据总线）

> 这 5 个文件是阶段之间唯一的接口。字段名写错不会报错，只会让下游 `KeyError` 或
> 整条时间轴错位——**抄字段，不要凭印象编**。

通用约定：

- 编码 **UTF-8，无 BOM**（`.srt` 例外，用 `utf-8-sig`）
- 时间单位一律 **秒，float**（`3.25` 就是 3.25 秒；没有毫秒整数、没有帧号）
- 区间是**半开还是闭**：本管线统一按「`start` 含、`end` 含边界但段间不重叠」处理，
  所有比较都带 `1e-6` 容差
- 数组顺序即时间顺序，不要依赖 `idx` 排序
- 写盘统一 `Path(...).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")`

---

## 1. `cuts.json` — 人工/半自动剪辑决策（输入）

由人或 Agent 写，是整条链的起点。

```json
{
  "source_duration": 312.4,
  "plan": "删掉 3 处口误 + 2 段跑题",
  "deletes": [
    {"start": 12.4, "end": 15.1},
    {"start": 88.02, "end": 90.6}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `source_duration` | float | ✅ | 原片时长（`ffprobe` 取），用来算最后一段 keep |
| `deletes` | array | ✅ | 要删的区间，可重叠、可乱序（`build_edl` 会 merge） |
| `deletes[].start` / `.end` | float | ✅ | 源片时间轴，秒 |
| `plan` | string | ❌ | 人读的决策说明，会原样带进 `segments.json` |

消费方：`build_edl.py`。

---

## 2. `segments.json` — 保留段 + 时间映射（`build_edl.py` 产出）

```json
{
  "source_duration": 312.4,
  "plan": "删掉 3 处口误 + 2 段跑题",
  "output_duration": 298.31,
  "removed_seconds": 14.09,
  "keep": [{"start": 0.0, "end": 12.4}, {"start": 15.1, "end": 88.02}],
  "deletes": [{"start": 12.4, "end": 15.1}],
  "mapping": [
    {"idx": 0, "src_start": 0.0, "src_end": 12.4,
     "out_start": 0.0, "out_end": 12.4, "length": 12.4}
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `keep` | array | 保留段（升序、不重叠），`cut.py` 读这个 |
| `deletes` | array | 原样回带的删除段 |
| `mapping` | array | 每段源↔成片映射；`length = src_end - src_start = out_end - out_start` |
| `output_duration` | float | 成片总长（= 所有 `length` 之和） |
| `removed_seconds` | float | `source_duration - output_duration` |

消费方：`cut.py`（读 `keep`）。

---

## 3. `timemap.json` — 源时间 ↔ 成片时间（`build_edl.py` / `cut.py` 产出）

**所有字幕、cues、场景时间轴换算的唯一依据。**

```json
{
  "source_duration": 312.4,
  "output_duration": 298.31,
  "mapping": [
    {"idx": 0, "src_start": 0.0, "src_end": 12.4,
     "out_start": 0.0, "out_end": 12.4, "length": 12.4}
  ],
  "removed": [[12.4, 15.1]]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `output_duration` | float | `compose_final.py` 拿它当全片长度（场景只覆盖一部分） |
| `mapping` | array | 字段同上；查找时按 `src_start <= t <= src_end` 命中 |
| `removed` | array[2] | 被删区间，纯记录用 |

**读法**（`make_srt.py` / `build_cues.py` 里的实现）：

```python
def src_to_out(t):
    for m in mapping:
        if m["src_start"] - 1e-6 <= t <= m["src_end"] + 1e-6:
            return m["out_start"] + (t - m["src_start"])
    return None      # None = 这个词被剪掉了，下游直接丢
```

消费方：`make_srt.py`、`build_cues.py`、`compose_final.py`。

---

## 4. `words.json` — ASR 词级时间（`transcribe.py` 产出）

```json
{
  "source": ".../raw.mp4",
  "model": "large-v3",
  "language": "zh",
  "duration": 312.4,
  "speech_ratio": 0.87,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 3.04,
      "text": "在招股书和长期承诺条款里面。",
      "words": [{"w": "在", "start": 0.0, "end": 0.1, "prob": 0.94}],
      "avg_logprob": -0.21,
      "no_speech_prob": 0.01
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `segments[].text` | string | 带标点；标点**不在** `words[]` 里，`make_srt` 负责贴回去 |
| `segments[].words[]` | array | **词级**时间：`w` / `start` / `end` / `prob` |
| `duration` | float | 语音覆盖到的时长 |

⚠️ 词字段是 `start` / `end`，**不是** `s` / `e`（跨片抄脚本最常见的 `KeyError`）。

消费方：`make_srt.py`、`build_cues.py`、`audit` 系列不直接读它。

---

## 5. `cues.json` — 台词表（`build_cues.py` 产出，成片时间轴）

**顶层是数组**，`audit_timing.py` 直接迭代。`--json` 从 `make_srt.py` 导出的也是这个结构。

```json
[
  {"i": 1, "start": 0.0, "end": 3.04, "text": "在招股书和长期承诺条款里面"},
  {"i": 2, "start": 3.04, "end": 6.18, "text": "藏着一份高达 5000 亿的承诺"}
]
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `i` | int | 从 1 开始的序号 |
| `start` / `end` | float | **成片**时间轴，秒 |
| `text` | string | 一句一条，已去尾标点、已套纠错表 |

`audit_timing.py` 也接受 `{"cues": [...]}` 包装（会拆开），但**新文件一律写裸数组**。

---

## 6. `fixes.json` — ASR 纠错表（可选输入）

```json
{"账言法": "障眼法", "编辑成本": "边际成本"}
```

放在 `<项目>/01-asr/fixes.json`，没有就是不纠错。按「越长越先替换」，
避免短词先命中把长词拆坏。

---

## 附：`TEXT` 字典（不是 JSON，但也是契约）

写在场景目录的 `TEXT`（`scene_kit.py` 顶部）：

```python
TEXT = {
    "s01_valuation_haircut": ("估值被砍掉三分之一", "两万亿的预期，一夜回到一万五"),
    "s03_ledger_807": ("807 亿，写在一行附注里"),      # 副标可省
}
```

键 = 场景文件主干；值 = 标题字符串或 `(标题, 副标)`。`K.scene_head(c, key, t)` 只从这里取字。
