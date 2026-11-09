# -*- coding: utf-8 -*-
"""审计：每个场景有没有**文字**落进字幕带（y 1300-1460）。

色块/图表可以允许（后期字幕带描边压得住），但文字叠文字一定难看。
用法: python audit_band.py            # 全跑
      python audit_band.py s01 s02    # 只跑匹配前缀
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import layout as L
import motion

B0, B1 = L.SUBTITLE_BAND
SKIP = {"demo_ledger.py"}


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    pats = sys.argv[1:]
    files = sorted((HERE / "scenes").glob("*.py"))
    bad = 0
    for p in files:
        if p.name in SKIP:
            continue
        if pats and not any(p.stem.startswith(x) for x in pats):
            continue
        mod = load(p)
        dur = float(getattr(mod, "DURATION", 10.0))
        hits: dict[str, list] = {}
        times = [round(i * 0.5, 2) for i in range(int(dur / 0.5) + 1)]
        for t in times:
            motion.TRACK[0] = True
            motion.TEXT_BOXES.clear()
            mod.frame(min(t, dur - 0.01))
            for b in motion.TEXT_BOXES:
                y0, y1 = b["box"][1], b["box"][3]
                if y1 > B0 and y0 < B1:
                    key = b["t"]
                    rec = hits.setdefault(key, [0.0, t, y0, y1])
                    rec[0] = max(rec[0], min(y1, B1) - max(y0, B0))
            motion.TRACK[0] = False
        if not hits:
            print(f"[OK  ] {p.name:30} 字幕带内无文字")
            continue
        bad += 1
        print(f"[BAD ] {p.name:30} {len(hits)} 处文字进了字幕带")
        for txt, (overlap, t, y0, y1) in sorted(hits.items(), key=lambda kv: -kv[1][0])[:8]:
            print(f"        「{txt[:16]}」 y{y0:.0f}-{y1:.0f}  压带 {overlap:.0f}px  首见 t={t:.1f}")
    print(f"\n合计 {bad} 个场景有文字进字幕带")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
