# -*- coding: utf-8 -*-
"""全链路冒烟：装 → 场景 → 六道验收 → 渲片段 → 合成 → 响度 → cues/srt。

在一个临时工作区里跑，不碰真实项目。
用法: python smoke_test.py [--keep]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent
PY = sys.executable

SCENE = '''# -*- coding: utf-8 -*-
import layout as L
import scene_kit as K
from motion import C, stage

DURATION = 12.55
KEY = "s01_valuation_haircut"


def bg_frame(t: float):
    # 背景提成模块级函数：check_layout 拿它渲「同一帧的纯背景」做差
    return K.canvas(t)


def frame(t: float):
    ts = L.lead(t)
    c = bg_frame(t)
    K.scene_head(c, KEY, ts)

    left, top, right, bottom = L.CONTENT
    a = stage(ts, 0.6, 0.6)
    if a > 0:
        c.rounded_rect((left, top + 60, right, top + 300), 18,
                       fill=(22, 32, 46, 235), outline=(127, 166, 201, 45), width=2,
                       opacity=a)
        c.text(left + 30, top + 90, "807", "bahn", 96, C.amber, opacity=a)
        c.text(left + 30, top + 210, "一笔表外附注，撑起两万亿估值", "yh", 34,
               C.text_dim, opacity=a)
    b = stage(ts, 1.6, 0.8)
    if b > 0:
        c.rounded_rect((left, 900, right, 1240), 18, fill=(22, 32, 46, 235),
                       outline=(127, 166, 201, 45), width=2, opacity=b)
        c.text(left + 30, 940, "收入 807 亿 / 现金流 128 亿", "yh", 38, C.text, opacity=b)
    c.rect((left, 1260, left + 120 + 60 * stage(ts, 2.0, 8.0), 1276),
           fill=(79, 209, 197, 200))
    return c.finish()
'''

WORDS = {
    "source": "raw.mp4", "duration": 30.0,
    "segments": [
        {"id": 0, "start": 0.0, "end": 3.0, "text": "在招股书和长期承诺条款里面。",
         "words": [{"w": "在", "start": 0.0, "end": 0.1, "prob": 0.9},
                   {"w": "招股书", "start": 0.1, "end": 0.8, "prob": 0.9},
                   {"w": "和", "start": 0.8, "end": 0.9, "prob": 0.9},
                   {"w": "长期", "start": 0.9, "end": 1.4, "prob": 0.9},
                   {"w": "承诺", "start": 1.4, "end": 1.9, "prob": 0.9},
                   {"w": "条款", "start": 1.9, "end": 2.4, "prob": 0.9},
                   {"w": "里面", "start": 2.4, "end": 3.0, "prob": 0.9}]},
        {"id": 1, "start": 3.0, "end": 6.0, "text": "藏着一份高达5000亿的承诺。",
         "words": [{"w": "藏着", "start": 3.0, "end": 3.4, "prob": 0.9},
                   {"w": "一份", "start": 3.4, "end": 3.8, "prob": 0.9},
                   {"w": "高达", "start": 3.8, "end": 4.2, "prob": 0.9},
                   {"w": "5000", "start": 4.2, "end": 5.0, "prob": 0.9},
                   {"w": "亿的", "start": 5.0, "end": 5.5, "prob": 0.9},
                   {"w": "承诺", "start": 5.5, "end": 6.0, "prob": 0.9}]},
    ],
}


def run(cmd, cwd=None, check=True, tail=6):
    print("  $", " ".join(str(c) for c in cmd[:6]), "..." if len(cmd) > 6 else "")
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.strip().splitlines()[-tail:]:
        print("    ", line)
    if check and r.returncode != 0:
        raise SystemExit(f"命令失败 rc={r.returncode}: {cmd}")
    return r


def main() -> int:
    keep = "--keep" in sys.argv
    root = Path(tempfile.mkdtemp(prefix="koubo_smoke_"))
    print(f"[root] {root}")

    print("\n== 0. install.py ==")
    run([PY, SKILL / "install.py", "--root", root, "--name", "冒烟片", "--title", "冒烟"])
    proj = root / "管线" / "成片" / "冒烟片"
    anim = proj / "03-动画"
    scripts = root / "管线" / "scripts"

    print("\n== 1. 写场景 + 收标题文案 ==")
    (anim / "scenes" / "s01_valuation_haircut.py").write_text(SCENE, encoding="utf-8")
    kit = anim / "scene_kit.py"
    text = kit.read_text(encoding="utf-8")
    text = text.replace('TEXT: dict[str, object] = {',
                        'TEXT: dict[str, object] = {\n    "s01_valuation_haircut": '
                        '("估值被砍掉三分之一", "两万亿的预期，一夜回到一万五"),')
    kit.write_text(text, encoding="utf-8")

    print("\n== 2. 中间件（模拟阶段 1/2 的产物）==")
    (proj / "02-剪辑").mkdir(parents=True, exist_ok=True)
    (proj / "02-剪辑" / "asr_verify").mkdir(parents=True, exist_ok=True)
    (proj / "02-剪辑" / "asr_verify" / "words.json").write_text(
        json.dumps(WORDS, ensure_ascii=False, indent=1), encoding="utf-8")
    (proj / "02-剪辑" / "timemap.json").write_text(json.dumps({
        "source_duration": 30.0, "output_duration": 12.55,
        "mapping": [{"idx": 0, "src_start": 0.0, "src_end": 12.55,
                     "out_start": 0.0, "out_end": 12.55, "length": 12.55}],
        "removed": []}, ensure_ascii=False, indent=1), encoding="utf-8")
    run([PY, scripts / "build_cues.py", proj / "02-剪辑" / "asr_verify" / "words.json",
         "-o", proj / "02-剪辑" / "cues.json", "--dump"])

    print("\n== 3. 合成素材（testsrc 当人物母版）==")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=13",
         "-f", "lavfi", "-i", "sine=frequency=420:duration=13",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", proj / "02-剪辑" / "03-超分.mp4"])

    print("\n== 4. 六道验收 ==")
    checks = [
        (["check_layout.py", "s01", "--step", "1.0"], 0),
        (["check_text.py", "S01", "--fps", "2"], 0),
        (["audit_band.py", "S01"], 0),
        (["audit_canvas.py"], 0),
        (["audit_timing.py", "s01", "--thresh", "300"], 0),
        (["audit_text_band.py", "--fps", "1"], 0),
    ]
    for args, _ in checks:
        r = run([PY] + args, cwd=anim, check=False)
        if r.returncode != 0:
            raise SystemExit(f"验收没过：{args[0]}")

    print("\n== 5. 构图验收图 + 三档对比图 ==")
    run([PY, scripts / "render_scene.py", "scenes/s01_valuation_haircut.py",
         "--stills", "1,3,6", "-o", "preview/s01_stills.png"], cwd=anim)
    run([PY, "make_check_png.py", "preview/s01_stills.png", "preview/构图验收.png"], cwd=anim)
    run([PY, "pos_options.py", "--video", proj / "02-剪辑" / "03-超分.mp4",
         "--at", "3", "--out", "preview/圆心三档.png"], cwd=anim)
    run([PY, "size_options.py", "--person", proj / "02-剪辑" / "03-超分.mp4",
         "--bg", proj / "02-剪辑" / "03-超分.mp4", "--person-at", "3", "--bg-at", "3",
         "--out", "preview/圆尺寸三档.png"], cwd=anim)

    print("\n== 6. 渲片段 + 合成 + 响度 ==")
    run([PY, "build_clips.py", "--force", "--jobs", "2", "--crf", "32", "s01"], cwd=anim)
    run([PY, "compose_final.py", "--out", proj / "02-剪辑" / "04-合成.mp4"], cwd=anim)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", proj / "02-剪辑" / "04-合成.mp4",
         "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", proj / "02-剪辑" / "05-成片.mp4"])
    probe = run(["ffprobe", "-v", "error", "-show_entries",
                 "format=duration:stream=codec_type", "-of", "csv=p=0",
                 proj / "02-剪辑" / "05-成片.mp4"], check=False)
    ebur = run(["ffmpeg", "-hide_banner", "-i", proj / "02-剪辑" / "05-成片.mp4",
                "-af", "ebur128", "-f", "null", "-"], check=False, tail=12)

    print("\n== 7. 字幕 ==")
    run([PY, scripts / "make_srt.py", "--proj", proj, "-o", proj / "final.srt"])

    print("\n[OK] 全链路通过")
    if keep:
        print(f"[keep] {root}")
    else:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
