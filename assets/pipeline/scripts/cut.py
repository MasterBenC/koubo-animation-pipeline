#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按剪辑决策把原片剪成粗剪，并写出时间映射（timemap）。

输入 `--segments`：
    - `<项目>/02-剪辑/segments.json`（build_edl.py 的产物，读 `keep[]`）
    - 或者直接给区间串：`"0-13.35,25.9-38.7"`
输出：
    `--out`      粗剪 mp4（画面/音频都按 keep 段重掐，重新编码，别用 -c copy）
    `--timemap`  原片时间 <-> 成片时间 的映射（字幕、动画时间轴都靠它）

用法：
    python cut.py --input <项目>/01-原片/raw.mp4 \
        --segments <项目>/02-剪辑/segments.json \
        --out <项目>/02-剪辑/02-粗剪.mp4 \
        --timemap <项目>/02-剪辑/timemap.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def read_keep(spec: str) -> list[tuple[float, float]]:
    """从 segments.json 或 "a-b,c-d" 里读出 keep 段。"""
    p = Path(spec)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("keep") or []
        keep = [(float(s["start"]), float(s["end"])) for s in data]
    else:
        keep = []
        for piece in spec.replace(";", ",").split(","):
            piece = piece.strip()
            if not piece:
                continue
            a, _, b = piece.partition("-")
            keep.append((float(a), float(b)))
    keep = [(a, b) for a, b in keep if b > a]
    if not keep:
        raise SystemExit("没有可用的保留段：检查 --segments 的内容")
    return keep


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ffprobe 失败：{path}\n{r.stderr[-500:]}")
    return json.loads(r.stdout)


def build_filter(keep: list[tuple[float, float]], has_audio: bool) -> tuple[str, list[str]]:
    parts, labels = [], []
    for i, (a, b) in enumerate(keep):
        parts.append(f"[0:v]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            parts.append(f"[0:a]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{i}]")
            labels += [f"[v{i}]", f"[a{i}]"]
        else:
            labels.append(f"[v{i}]")
    n = len(keep)
    if has_audio:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[outv][outa]")
    else:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=0[outv]")
    return ";".join(parts), (["-map", "[outv]", "-map", "[outa]"] if has_audio
                             else ["-map", "[outv]", "-an"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="原片")
    ap.add_argument("--segments", required=True, help="segments.json 或 a-b,c-d")
    ap.add_argument("--out", required=True, help="粗剪输出 mp4")
    ap.add_argument("--timemap", default=None, help="timemap.json 输出路径（默认与 out 同目录）")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令，不动手")
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.exists():
        print(f"input not found: {src}", file=sys.stderr)
        return 2
    keep = read_keep(args.segments)
    info = probe(src)
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    src_dur = float(info.get("format", {}).get("duration", keep[-1][1]))

    flt, maps = build_filter(keep, has_audio)
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-filter_complex", flt, *maps,
           "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
           "-pix_fmt", "yuv420p"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-movflags", "+faststart", str(out)]

    if args.dry_run:
        print(" ".join(cmd))
    else:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-1500:], file=sys.stderr)
            return 1
        print(f"[cut] {len(keep)} 段 -> {out}")

    # timemap：成片时间轴 = 各段长度累加
    mapping, t_out = [], 0.0
    for i, (a, b) in enumerate(keep):
        length = round(b - a, 3)
        mapping.append({"idx": i, "src_start": round(a, 3), "src_end": round(b, 3),
                        "out_start": round(t_out, 3), "out_end": round(t_out + length, 3),
                        "length": length})
        t_out += length
    tm = {"source_duration": round(src_dur, 3),
          "output_duration": round(t_out, 3),
          "mapping": mapping,
          "removed": []}
    dest = Path(args.timemap) if args.timemap else out.with_name("timemap.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(tm, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[timemap] 成片 {tm['output_duration']:.2f}s（原 {tm['source_duration']:.2f}s，"
          f"删 {tm['source_duration'] - tm['output_duration']:.2f}s）-> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
