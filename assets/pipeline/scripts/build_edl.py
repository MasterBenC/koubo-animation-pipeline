#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""由 cuts.json 算出 keep 段、成片时间映射、以及 cut.py 的 --segments 参数。

产出:
    segments.json   机器可读：keep[] / deletes[] / 映射后的成片时长
    timemap.json    源时间 <-> 成片时间 双向映射（字幕和动画都要用）
    segments.txt    cut.py --segments 的参数字符串
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def merge(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1] + 1e-6:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-keep", type=float, default=0.12)
    args = ap.parse_args()

    cuts = json.loads(Path(args.cuts).read_text(encoding="utf-8"))
    dur = float(cuts["source_duration"])
    dels = merge([(d["start"], d["end"]) for d in cuts["deletes"]])

    keep = []
    cur = 0.0
    for s, e in dels:
        if s - cur >= args.min_keep:
            keep.append((round(cur, 3), round(s, 3)))
        cur = max(cur, e)
    if dur - cur >= args.min_keep:
        keep.append((round(cur, 3), round(dur, 3)))

    # 映射表：每段 keep 给出 source_start / out_start / length
    mapping = []
    out_t = 0.0
    for i, (s, e) in enumerate(keep):
        length = round(e - s, 3)
        mapping.append({"idx": i, "src_start": s, "src_end": e,
                        "out_start": round(out_t, 3), "out_end": round(out_t + length, 3),
                        "length": length})
        out_t += length
    total_out = round(out_t, 3)

    def src_to_out(t: float) -> float:
        for m in mapping:
            if m["src_start"] - 1e-6 <= t <= m["src_end"] + 1e-6:
                return round(m["out_start"] + (t - m["src_start"]), 3)
        # 落在删除区：吸附到最近的段边界
        best = min(mapping, key=lambda m: min(abs(t - m["src_start"]), abs(t - m["src_end"])))
        return best["out_start"] if abs(t - best["src_start"]) < abs(t - best["src_end"]) else best["out_end"]

    payload = {
        "source_duration": dur,
        "plan": cuts.get("plan"),
        "output_duration": total_out,
        "removed_seconds": round(dur - total_out, 3),
        "keep": [{"start": s, "end": e} for s, e in keep],
        "deletes": cuts["deletes"],
        "mapping": mapping,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "segments.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    tm = {
        "source_duration": dur,
        "output_duration": total_out,
        "mapping": mapping,
        "removed": [[round(s, 3), round(e, 3)] for s, e in dels],
    }
    (out / "timemap.json").write_text(json.dumps(tm, ensure_ascii=False, indent=1), encoding="utf-8")

    seg_arg = ",".join(f"{s:.3f}-{e:.3f}" for s, e in keep)
    (out / "segments.txt").write_text(seg_arg, encoding="utf-8")

    # 抽查：几个关键时间点映射
    checks = [0.5, 5.0, 40.0, 116.9, 122.2, 141.9, 183.5, 192.4, 230.5, 254.7, 273.5, 287.6, 294.0]
    print(f"keep {len(keep)} 段，删除 {len(dels)} 处，成片 {total_out:.2f}s（原 {dur:.2f}s，删 {dur-total_out:.2f}s）")
    print("抽查映射：")
    for t in checks:
        print(f"  源 {t:7.2f}s -> 成片 {src_to_out(t):7.2f}s")
    print(f"\n--segments ({len(seg_arg)} 字符):\n{seg_arg[:400]}{'...' if len(seg_arg) > 400 else ''}")
    print(f"\nwrote {out/'segments.json'} / timemap.json / segments.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
