# -*- coding: utf-8 -*-
"""把所有场景批量渲成片段，跳过已渲好的。多进程分块渲染。

输出 scenes/clips/<name>.mp4（1080x1920 / 30fps / CRF 17）

每个场景按帧切成 --jobs 块并行渲，再无损拼接。单帧 200-500ms，
串行渲完整片要半小时以上，分块能把时间压到个位数分钟。

用法:
    python build_clips.py                # 只渲缺的
    python build_clips.py --force        # 全部重渲
    python build_clips.py S07 S08        # 只渲指定编号
    python build_clips.py --jobs 6       # 并发数
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layout as L

RENDER = HERE.parents[2] / "scripts" / "render_scene.py"
FPS = 30


def render_scene(sid: str, name: str, dur: float, out: Path, jobs: int, crf: int) -> bool:
    src = HERE / "scenes" / f"{name}.py"
    if not src.exists():
        print(f"[skip] {sid} 缺场景文件 {src.name}")
        return True
    n_total = int(round(dur * FPS))
    bounds = [int(round(i * n_total / jobs)) for i in range(jobs + 1)]

    tmpdir = Path(tempfile.mkdtemp(prefix=f"chunk_{name}_", dir=str(HERE / "preview")))
    parts: list[Path] = []

    def run(k: int):
        a, b = bounds[k], bounds[k + 1]
        if b <= a:
            return
        p = tmpdir / f"p{k:02d}.mp4"
        cmd = [sys.executable, str(RENDER), str(src), "-o", str(p),
               "--fps", str(FPS), "--crf", str(crf), "--preset", "medium",
               "--from", f"{a / FPS:.6f}", "--to", f"{b / FPS:.6f}"]
        r = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{sid} chunk {k} 失败:\n{r.stderr[-800:]}")
        parts.append(p)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(run, range(jobs)))

    parts.sort(key=lambda p: p.name)
    lst = tmpdir / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-800:])
        return False
    for f in parts:
        f.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    tmpdir.rmdir()
    el = time.time() - t0
    print(f"    [done] {out.name} {n_total} 帧 {el:.0f}s ({n_total / el:.1f} fps) "
          f"{out.stat().st_size / 1e6:.2f} MB", flush=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="只渲这些编号，例如 S07 S08")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--crf", type=int, default=17)
    args = ap.parse_args()

    clips = HERE / "scenes" / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    todo = [s for s in L.SCENE_SLOTS if not args.only or s[0] in args.only]

    t_all = time.time()
    for sid, name, a, b, dur in todo:
        out = clips / f"{name}.mp4"
        if out.exists() and not args.force:
            print(f"[skip] {sid} 已有片段")
            continue
        print(f"[render] {sid} {name}  {dur:.2f}s / {int(round(dur * FPS))} 帧 "
              f"jobs={args.jobs}", flush=True)
        if not render_scene(sid, name, dur, out, args.jobs, args.crf):
            return 1
    print(f"[all done] {time.time() - t_all:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
