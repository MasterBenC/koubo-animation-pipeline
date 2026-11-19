#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 ASR 词表变成「台词表」cues.json（成片时间轴），给场景挂节拍和 audit_timing 用。

和 make_srt.py 共用同一套断句逻辑（直接 import 它，不复制一份）：标点贴回词、
按 timemap 映射到成片时间、按标点/换段/停顿切 cue、套纠错表。

为什么必须过 timemap：场景和字幕都在**成片时间轴**上；直接拿原片时间会整体错位
（被删掉的段落越长，错得越多，而且不报错）。

用法：
    python build_cues.py <项目>/02-剪辑/asr_verify/words.json -o <项目>/02-剪辑/cues.json
    python build_cues.py words.json -o cues.json --timemap <项目>/02-剪辑/timemap.json
    python build_cues.py words.json -o cues.json --max-chars 16 --dump

产物格式（顶层是数组，audit_timing.py 直接读）：
    [{"i": 1, "start": 0.0, "end": 3.04, "text": "在招股书和长期承诺条款里面"}, ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_srt as ms


def find_timemap(words_json: Path) -> Path | None:
    """向上 4 层找 timemap.json（words.json 常在 02-剪辑/asr_verify/ 下）。"""
    for base in [words_json.parent, *words_json.parents][:4]:
        cand = base / "timemap.json"
        if cand.exists():
            return cand
    return None


def find_project(words_json: Path) -> Path:
    """向上找项目根（判据：有 01-asr 或 02-剪辑 子目录）。"""
    for base in [words_json.parent, *words_json.parents][:5]:
        if (base / "01-asr").is_dir() or (base / "02-剪辑").is_dir():
            return base
    return words_json.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("words", help="ASR 的 words.json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--timemap", default=None, help="不给就自动向上找 timemap.json")
    ap.add_argument("--max-chars", type=int, default=18)
    ap.add_argument("--fixes", default=None, help="纠错表 json，默认 <项目>/01-asr/fixes.json")
    ap.add_argument("--no-remap", action="store_true", help="words.json 已经是成片时间轴时用")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    words_path = Path(args.words).resolve()
    if not words_path.exists():
        print(f"找不到 {words_path}", file=sys.stderr)
        return 2
    data = json.loads(words_path.read_text(encoding="utf-8-sig"))
    segments = data["segments"] if isinstance(data, dict) else data

    fixes = (ms.load_fixes_file(Path(args.fixes)) if args.fixes
             else ms.load_fixes(find_project(words_path)))

    if args.no_remap:
        s2o, out_dur = (lambda t: t), float(data.get("duration", 0) or 0)
    else:
        tm_path = Path(args.timemap) if args.timemap else find_timemap(words_path)
        if not tm_path or not Path(tm_path).exists():
            print("[!] 找不到 timemap.json：cues 必须落在成片时间轴上。\n"
                  "    要么先跑 cut.py/build_edl.py 生成 timemap.json，"
                  "要么确认 words.json 已经是成片时间轴后加 --no-remap", file=sys.stderr)
            return 2
        tm = json.loads(Path(tm_path).read_text(encoding="utf-8-sig"))
        spans = [(m["src_start"], m["src_end"], m["out_start"]) for m in tm["mapping"]]

        def s2o(t: float):
            for a, b, o in spans:
                if a - 1e-6 <= t <= b + 1e-6:
                    return o + (t - a)
            return None
        out_dur = float(tm["output_duration"])

    words = ms.remap(segments, s2o)
    cues = ms.build_cues(words, max_chars=args.max_chars)

    rows, n, prev_end = [], 0, 0.0
    for cue in cues:
        txt = ms.cue_text(cue, fixes)
        if not txt:
            continue
        a = max(prev_end, cue[0]["s"])
        b = min(out_dur, cue[-1]["e"]) if out_dur else cue[-1]["e"]
        if b - a < 0.30:
            b = a + 0.30
        n += 1
        prev_end = b
        rows.append({"i": n, "start": round(a, 3), "end": round(b, 3), "text": txt})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[cues] {len(rows)} 条 -> {out}")
    if args.dump:
        for r in rows:
            print(f"{r['i']:4d} {r['start']:7.2f}-{r['end']:7.2f}  {r['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
