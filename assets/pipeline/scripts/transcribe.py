#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""口播转写：faster-whisper -> 词级时间戳 + SRT + 人读逐字稿。

用法:
    python transcribe.py 原片.mp4 -o 输出目录 [--model large-v3] [--lang zh]

产出:
    <out>/words.json      机器可读：segments[] / words[] / 每秒语音占比
    <out>/raw.srt         带标点的句子级字幕（后续人工合并成 1-2 行/条）
    <out>/逐字稿.md        人读版：时间码 + 句子 + 词级时间 + 可疑 filler 标记
    <out>/audio.wav       16k mono 提取音轨（复用，省一次解码）

设计约定:
  - 不做任何"改写"，whisper 输出什么就是什么；纠错在人工环节做。
  - 每个词给出 start/end/probability，供后续 cut.py --filler 和 karaoke 使用。
  - 额外算 fillers：[嗯 呃 啊 那个 就是说 然后 这个 对吧 你知道] 的命中位置。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

FILLER_PATTERNS = [
    "嗯", "呃", "额", "啊", "哦", "唉", "诶",
    "那个", "这个", "就是说", "然后呢", "对吧", "你知道", "怎么说呢",
    "反正", "其实吧", "就那种",
]


def extract_audio(src: Path, dst: Path, sr: int = 16000) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
        str(dst),
    ]
    subprocess.run(cmd, check=True)


def load_wav_16k(path: Path) -> "object":
    """用标准库读 16k mono s16 WAV -> float32 ndarray。

    绕开 faster-whisper 内置的 PyAV 解码：av>=19 去掉了 metadata_errors 参数，
    faster-whisper 1.2.1 会直接 TypeError。我们自己解码，不吃这个版本耦合。
    """
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getframerate() != 16000 or w.getsampwidth() != 2:
            raise ValueError(f"expected 16k mono s16 wav, got {w.getnchannels()}ch "
                             f"{w.getframerate()}Hz {w.getsampwidth()*8}bit")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def fmt_ts(sec: float, srt: bool = False) -> str:
    if srt:
        h = int(sec // 3600)
        m = int(sec % 3600 // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        if ms == 1000:
            ms = 999
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    m = int(sec // 60)
    s = sec % 60
    return f"{m:02d}:{s:06.3f}"


def read_hms(t: str) -> str:
    m = int(float(t) // 60)
    s = float(t) - m * 60
    return f"{m:02d}:{s:06.3f}"


def build_srt(segments: list[dict]) -> str:
    out = []
    for i, seg in enumerate(segments, 1):
        out.append(str(i))
        out.append(f"{fmt_ts(seg['start'], True)} --> {fmt_ts(seg['end'], True)}")
        out.append(seg["text"].strip())
        out.append("")
    return "\n".join(out)


def find_fillers(words: list[dict], text: str) -> list[dict]:
    """在词序列里找语气词/口头禅；返回带时间码的命中项。"""
    hits = []
    for i, w in enumerate(words):
        tok = w["w"].strip()
        if tok in FILLER_PATTERNS:
            hits.append({"kind": "word", "token": tok, "start": w["start"], "end": w["end"]})
    # 整句里出现但分词没切出来（中文分词常把"那个"并进词里）
    for pat in FILLER_PATTERNS:
        for m in re.finditer(re.escape(pat), text):
            # 只留"独立成句/句首"位置的高置信度命中，避免误伤实词（"那个东西"）
            idx = m.start()
            before = text[max(0, idx - 1):idx]
            after = text[m.end():m.end() + 1]
            if before in ("", "，", "。", "！", "？", "…", " ") and after in ("", "，", "。", "！", "？", "…", " "):
                hits.append({"kind": "phrase", "token": pat, "snippet": text[max(0, idx - 6):m.end() + 6]})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default=None, help="输出目录，默认 <input_stem>_asr")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--model-root", default=r"C:\Users\benhu\Desktop\档案001\work\models")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--no-vad", action="store_true")
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.exists():
        print(f"input not found: {src}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else src.with_name(src.stem + "_asr")
    out.mkdir(parents=True, exist_ok=True)

    wav = out / "audio.wav"
    if not wav.exists():
        t0 = time.time()
        extract_audio(src, wav)
        print(f"[audio] {wav.name} {wav.stat().st_size/1e6:.1f}MB in {time.time()-t0:.1f}s")

    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         download_root=args.model_root, cpu_threads=args.threads)
    print(f"[model] {args.model} loaded in {time.time()-t0:.1f}s")

    t1 = time.time()
    segments_iter, info = model.transcribe(
        load_wav_16k(wav),
        language=args.lang,
        beam_size=args.beam,
        word_timestamps=True,
        vad_filter=not args.no_vad,
        vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=120),
        condition_on_previous_text=False,
        initial_prompt="以下是普通话口播，请使用简体中文与标准标点。",
    )

    segments = []
    for i, s in enumerate(segments_iter):
        words = [
            {"w": w.word, "start": round(w.start, 3), "end": round(w.end, 3),
             "prob": round(getattr(w, "probability", 0.0), 3)}
            for w in (s.words or [])
        ]
        segments.append({
            "id": i,
            "start": round(s.start, 3),
            "end": round(s.end, 3),
            "text": s.text,
            "words": words,
            "avg_logprob": round(s.avg_logprob, 4),
            "no_speech_prob": round(s.no_speech_prob, 4),
        })
        print(f"  [{i:03d}] {read_hms(s.start)}-{read_hms(s.end)} {s.text.strip()}", flush=True)

    dur = segments[-1]["end"] if segments else 0.0
    print(f"[asr] {len(segments)} segments, speech to {dur:.2f}s, took {time.time()-t1:.1f}s")

    all_words = [w for s in segments for w in s["words"]]
    total_speech = sum(s["end"] - s["start"] for s in segments)
    payload = {
        "source": str(src),
        "model": args.model,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration": round(dur, 3),
        "speech_seconds": round(total_speech, 3),
        "speech_ratio": round(total_speech / dur, 3) if dur else 0,
        "segments": segments,
    }
    (out / "words.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "raw.srt").write_text(build_srt(segments), encoding="utf-8")

    lines = ["# 逐字稿（自动转写，未改写）", "",
             f"- 源文件: `{src.name}`  时长 {dur:.2f}s  语音占比 {payload['speech_ratio']*100:.0f}%",
             f"- 模型: {args.model} / {info.language} ({info.language_probability:.2f})", "",
             "| # | 起止 | 文本 | 词级时间（可选） | filler |",
             "|---:|---|---|---|---|"]
    for s in segments:
        f_hits = find_fillers(s["words"], s["text"])
        f_txt = "、".join(sorted({h["token"] for h in f_hits})) or ""
        raw_line = " ".join(f"{w['w']}({w['start']:.2f}-{w['end']:.2f})" for w in s["words"])
        low_conf = [w for w in s["words"] if w["prob"] < 0.6]
        flag = ""
        if s["no_speech_prob"] > 0.4:
            flag += "静音嫌疑 "
        if low_conf:
            flag += f"低置信×{len(low_conf)} "
        if flag:
            f_txt = (f_txt + " / " + flag).strip(" /")
        txt = s["text"].strip().replace("|", "\\|")
        lines.append(f"| {s['id']:03d} | {read_hms(s['start'])}–{read_hms(s['end'])} | {txt} | {raw_line} | {f_txt} |")
    (out / "逐字稿.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[ok] {out}")
    print(f"     words.json / raw.srt / 逐字稿.md / audio.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
