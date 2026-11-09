#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 ASR 词表生成对齐到「成片时间轴」的字幕（SRT）。

不做烧录——用户后期自己统一烧字幕，这里只负责给一份时间准确的文本。

做法：
    1. 读 01-asr/words.json（逐字时间，源片时间轴）
    2. 把 segment.text 里的标点"贴回"到对应词上（whisper 的 word 级时间戳不带标点）
    3. 用 02-剪辑/timemap.json 把每个字的起止映射到成片时间轴（被剪掉的句子自然掉出去）
    4. 按标点 / 换段 / 停顿切 cue
    5. 套 ASR 纠错表
    6. 写 SRT

用法:
    python make_srt.py --proj "…/口播-01" -o "…/final.srt"
    python make_srt.py --proj "…/口播-01" --dump
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# ASR 听错的词。按"越长越先替换"排序，避免短词先命中把长词拆坏。
FIXES = {
    "账目账言法": "障眼法",
    "账言法": "障眼法",
    "这份SE的": "这份S-1的",
    "现在SE的": "现在S-1的",
    "Zeropic": "Anthropic",
    "编辑成本": "边际成本",
    "进调": "尽调",
    "表外付注": "表外附注",
    "付注": "附注",
    "与融资租赁成约": "与融资租赁承诺",
    "Cloud": "Claude",
    "试梦率": "市梦率",
    "AI洋谋": "AI阳谋",
    "洋谋": "阳谋",
    "算力卖身器": "算力卖身契",
    "卖身器": "卖身契",
    "森罗万象拆解本质": "森罗万象，拆解本质",
}

PUNCT = "，。？！、；：,.?!;:…—"
TAIL_TRIM = "，。、；：,.;: "


def load_segments(proj: Path):
    d = json.loads((proj / "01-asr" / "words.json").read_text(encoding="utf-8"))
    return d["segments"]


def attach_punct(seg) -> list[dict]:
    """把 seg['text'] 里的标点贴到对应词后面。"""
    text = "".join(seg["text"].split())
    words = [w for w in seg["words"] if w["w"].strip()]
    out, p = [], 0
    for w in words:
        tok = "".join(w["w"].split())
        idx = text.find(tok, p)
        if idx < 0:
            out.append({"w": tok, "s": float(w["start"]), "e": float(w["end"]), "p": ""})
            continue
        p = idx + len(tok)
        q = ""
        while p < len(text) and text[p] in PUNCT:
            q += text[p]
            p += 1
        out.append({"w": tok, "s": float(w["start"]), "e": float(w["end"]), "p": q})
    return out


def load_mapper(proj: Path):
    tm = json.loads((proj / "02-剪辑" / "timemap.json").read_text(encoding="utf-8"))
    spans = [(m["src_start"], m["src_end"], m["out_start"]) for m in tm["mapping"]]

    def s2o(t: float):
        for a, b, o in spans:
            if a - 1e-6 <= t <= b + 1e-6:
                return o + (t - a)
        return None

    return s2o, float(tm["output_duration"])


def remap(segments, s2o):
    """→ 一串词，带成片时间 + 标点 + 段号。被剪掉的词直接丢弃。"""
    out = []
    for si, seg in enumerate(segments):
        for w in attach_punct(seg):
            mid = (w["s"] + w["e"]) / 2
            o = s2o(mid)
            if o is None:
                continue
            a, b = s2o(w["s"]), s2o(w["e"])
            a = o if a is None else a
            b = o + (w["e"] - w["s"]) if b is None else b
            out.append({"w": w["w"], "p": w["p"], "s": a, "e": max(b, a + 0.06), "seg": si})
    return out


def _numeric_tail(s: str) -> bool:
    return bool(s) and (s[-1].isdigit() or s[-1] in ".%万亿")


def _numeric_head(s: str) -> bool:
    return bool(s) and (s[0].isdigit() or s[0] in ".%万亿")


def build_cues(words, max_chars=18, max_gap=0.42, max_dur=5.2):
    cues, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            cues.append(cur)
            cur = []

    for w in words:
        if cur:
            gap = w["s"] - cur[-1]["e"]
            new_seg = w["seg"] != cur[-1]["seg"]
            nxt = sum(len(x["w"]) for x in cur) + len(w["w"])
            over = nxt > max_chars or (w["e"] - cur[0]["s"]) > max_dur
            # 别在数字和单位之间切：807 / 亿美金、1 / .5万亿
            glued = (_numeric_tail(cur[-1]["w"]) and _numeric_head(w["w"]))
            if (new_seg and not glued) or gap > max_gap or (over and not glued):
                flush()
        cur.append(w)
        # 词自带标点（whisper 有时候把逗号贴在词尾）也要断句
        # 例外：数字后面那个小数点（"1." "1.5"）不是句号
        tail = w["w"][-1] if w["w"] else ""
        num_dot = tail == "." and all(ch in "0123456789." for ch in w["w"])
        if w["p"] or (tail in PUNCT and not num_dot):
            flush()
    flush()

    # 只有一两个字的碎 cue：句首的并到下一句，句中的并回上一句
    def nchar(c):
        return len("".join(x["w"] for x in c))

    def ends_sentence(c):
        return bool(c) and (c[-1]["p"][:1] in "。？！" or c[-1]["w"][-1:] in "。？！")

    merged: list[list] = []
    i = 0
    while i < len(cues):
        c = cues[i]
        if nchar(c) <= 2:
            if merged and i + 1 < len(cues) and ends_sentence(merged[-1]):
                merged.append(list(c) + cues[i + 1])
                i += 2
                continue
            if merged:
                merged[-1] = merged[-1] + c
                i += 1
                continue
            if i + 1 < len(cues):
                merged.append(list(c) + cues[i + 1])
                i += 2
                continue
        merged.append(list(c))
        i += 1
    return merged


def apply_fixes(text: str) -> str:
    for k in sorted(FIXES, key=len, reverse=True):
        text = text.replace(k, FIXES[k])
    return text


def cue_text(cue) -> str:
    raw = "".join(x["w"] + x["p"] for x in cue)
    for a, b in ((",", "，"), ("?", "？"), ("!", "！"), (":", "："), (";", "；")):
        raw = raw.replace(a, b)
    raw = apply_fixes(raw).strip()
    while raw and raw[-1] in TAIL_TRIM:
        raw = raw[:-1]
    return raw.strip()


def ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proj", required=True)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--max-chars", type=int, default=18)
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--json", default=None, help="同时导出 cue 列表 json")
    args = ap.parse_args()

    proj = Path(args.proj).resolve()
    s2o, out_dur = load_mapper(proj)
    words = remap(load_segments(proj), s2o)
    cues = build_cues(words, max_chars=args.max_chars)

    lines, rows, n = [], [], 0
    prev_end = 0.0

    # 先整理成 (起, 止, 文本)，把"以标点开头"的残句并到上一句
    flat: list[dict] = []
    for cue in cues:
        txt = cue_text(cue)
        if not txt:
            continue
        flat.append({"s": cue[0]["s"], "e": cue[-1]["e"], "t": txt})

    tidy: list[dict] = []
    for c in flat:
        if tidy and c["t"][:1] in "。，、；：？！" and not tidy[-1]["t"].endswith(("。", "？", "！")):
            tidy[-1]["e"] = c["e"]
            tidy[-1]["t"] = tidy[-1]["t"] + c["t"]
        else:
            tidy.append(dict(c))

    for c in tidy:
        txt = c["t"].strip()
        if not txt:
            continue
        a = max(prev_end, c["s"])
        b = min(out_dur, c["e"])
        if b - a < 0.30:
            b = a + 0.30
        n += 1
        prev_end = b
        lines += [str(n), f"{ts(a)} --> {ts(b)}", txt, ""]
        rows.append({"i": n, "start": round(a, 3), "end": round(b, 3), "text": txt})

    if args.dump:
        for r in rows:
            print(f"{r['i']:4d} {r['start']:7.2f}-{r['end']:7.2f}  {r['text']}")
    else:
        out = Path(args.out or (proj / "final.srt"))
        out.write_text("\n".join(lines), encoding="utf-8-sig")
        print(f"[srt] {n} 条 -> {out}")

    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
