# -*- coding: utf-8 -*-
"""把 skill 里的工具链安装到一个工作区，并搭好一支新片子的骨架。

用法：
    python install.py --root "D:\\我的片子" --name 口播-02 --title "英伟达财报拆解"

做的事：
    1. <root>/管线/scripts/           ← 通用脚本（ASR、渲染、看片）
    2. <root>/管线/组件/             ← 片尾组件
    3. <root>/管线/成片/<name>/      ← 01-原片 / 01-asr / 02-剪辑 / 03-动画/scenes
    4. <root>/管线/成片/<name>/03-动画/ ← 版式、场景工具箱、渲染、五道验收
    5. <root>/管线/成片/<name>/BRIEF.md
    6. <root>/管线/生产手册.md       ← 流程速查（从 skill 复制）

已存在同名工程时默认不覆盖，加 --force 才覆盖工具文件（不会删你的场景）。
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets" / "pipeline"

BRIEF = """# BRIEF — {name}

> 立项卡。开工前填完，后面每一步都回来对一眼。

## 基本信息
- **项目名**：{name}
- **片子标题**：{title}
- **原始素材**：（路径 / 时长 / 分辨率 / 帧率）
- **成片时长目标**：约 ___ 秒
- **画面**：1080×1920 / 30fps / H.264

## 受众与平台
- **平台**：抖音 / 视频号 / 小红书（竖屏）
- **受众**：（谁看？他关心什么？）
- **发布形态**：单条短视频 / 系列第几集

## 内容
- **一句话主张**：（这支片子只讲一件事，写出来）
- **结构**：（钩子 → 展开 → 收束，各段几秒）
- **必须保留的台词**：（金句 / 数据 / 结论）
- **必须删掉的**：（跑题、重复、口误）

## 视觉
- **调性**：（冷静克制 / 强冲击 / 轻快）
- **主色**：（深色底 + 强调色？）
- **动画强度**：（A 克制：只做图表；B 中等：加结构图；C 强：加拟物动效）

## 交付
- [ ] 成片 mp4（-14 LUFS）
- [ ] final.srt（字幕**绝不烧进画面**，用户后期自己烧）
- [ ] QA.md（验收记录）
- [ ] 片尾组件已挂载

## 待确认
- [ ] 版式（圆头像大小 / 位置）
- [ ] 动画方向（2–3 选 1）
- [ ] 是否加 BGM
- [ ] 是否加生成素材
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="安装口播动画流水线并搭新片子")
    ap.add_argument("--root", required=True, help="工作区根目录，例如 D:\\我的片子")
    ap.add_argument("--name", required=True, help="项目名，例如 口播-02")
    ap.add_argument("--title", default="", help="片子标题")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的工具文件")
    args = ap.parse_args()

    if not ASSETS.exists():
        print(f"找不到资源目录：{ASSETS}")
        return 1

    root = Path(args.root)
    pipe = root / "管线"
    proj = pipe / "成片" / args.name
    anim = proj / "03-动画"

    # 1) 通用脚本
    (pipe / "scripts").mkdir(parents=True, exist_ok=True)
    for f in (ASSETS / "scripts").glob("*.py"):
        shutil.copyfile(f, pipe / "scripts" / f.name)

    # 2) 片尾组件
    (pipe / "组件").mkdir(parents=True, exist_ok=True)
    for f in (ASSETS / "组件").iterdir():
        if f.is_file():
            shutil.copyfile(f, pipe / "组件" / f.name)

    # 3) 项目目录
    for sub in ("01-原片", "01-asr", "02-剪辑", "03-动画/scenes"):
        (proj / sub).mkdir(parents=True, exist_ok=True)

    # 4) 项目级工具
    tpl = ASSETS / "成片" / "_模板" / "03-动画"
    for f in tpl.iterdir():
        if not f.is_file():
            continue
        dst = anim / f.name
        if dst.exists() and not args.force:
            continue
        shutil.copyfile(f, dst)

    # 4.5) 人类可读的生产手册
    manual = ASSETS / "生产手册.md"
    if manual.exists():
        shutil.copyfile(manual, pipe / "生产手册.md")

    # 5) BRIEF
    brief = proj / "BRIEF.md"
    if not brief.exists() or args.force:
        brief.write_text(BRIEF.format(name=args.name, title=args.title or "（待定）"),
                         encoding="utf-8", newline="\n")

    print(f"[ok] 工作区：{root}")
    print(f"     工程：{proj}")
    print()
    print("下一步：")
    print(f"  1. 把原片放进 {proj / '01-原片'}")
    print("  2. 填 BRIEF.md")
    print(f"  3. python \"{pipe / 'scripts' / 'transcribe.py'}\" <原片> -o \"{proj / '01-asr'}\"")
    print("  4. 量人物头部 → 改 03-动画\\layout.py → 出构图验收图给用户确认")
    print("  5. 按 references/pipeline.md 往下走")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
