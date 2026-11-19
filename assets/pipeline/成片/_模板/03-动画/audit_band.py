# -*- coding: utf-8 -*-
"""验收③：字幕带内有没有**文字**（竖屏默认 y 1300–1460）。

分工（别看串了）：
    ③ `audit_band.py`        只查「文字 × 字幕带」这一条，逐场定位、报压带像素数
    ⑥ `audit_text_band.py`   查「文字 × 整个允许框」（上沿 140 / 下沿 1290 / 左右 72–1008）
    ① `check_layout.py`      查「像素（含图形） × 圆头像 / 字幕带 / 安全区」

    也就是说：图形（色块、图表、卡片）进字幕带的锅归 ① 管；
    这里只统计 `c.text()` 画出来的字。

用法: python audit_band.py            # 全跑
      python audit_band.py s01 S02    # 只跑匹配的（大小写不敏感）
"""
from __future__ import annotations

import sys

import _paths

_paths.ensure_import_path()

import layout as L          # noqa: E402
import motion               # noqa: E402

B0, B1 = L.SUBTITLE_BAND


def main() -> int:
    keys = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = _paths.discover_scenes()
    if keys:
        files = [p for p in files if _paths.matches(p, keys)]
    if not files:
        print("[!] 没有匹配的场景文件（只认 sNN_*.py）")
        return 1

    bad = 0
    for p in files:
        mod = _paths.load_scene(p)
        dur = _paths.duration(mod)
        hits: dict[str, list] = {}
        times = [round(i * 0.5, 2) for i in range(int(dur / 0.5) + 1)]
        for t in times:
            with motion.text_tracking() as boxes:
                mod.frame(min(t, dur - 0.01))
                for b in list(boxes):
                    y0, y1 = b["box"][1], b["box"][3]
                    if y1 > B0 and y0 < B1:
                        key = b["t"]
                        rec = hits.setdefault(key, [0.0, t, y0, y1])
                        rec[0] = max(rec[0], min(y1, B1) - max(y0, B0))
        if not hits:
            print(f"[OK  ] {p.name:30} 字幕带内无文字")
            continue
        bad += 1
        print(f"[BAD ] {p.name:30} {len(hits)} 处文字进了字幕带")
        for txt, (overlap, t, y0, y1) in sorted(hits.items(), key=lambda kv: -kv[1][0])[:8]:
            print(f"        「{txt[:16]}」 y{y0:.0f}-{y1:.0f}  压带 {overlap:.0f}px  首见 t={t:.1f}")
    print(f"\n合计 {bad} 个场景有文字进字幕带（带 {B0}-{B1}）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
