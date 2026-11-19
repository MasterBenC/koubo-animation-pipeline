# -*- coding: utf-8 -*-
"""公共路径与场景发现：所有验收/渲染脚本共用这一份，别再各写一套 parents[N]。

为什么需要：
    `03-动画` 在不同片子里的深度是固定的（`<工作区>/管线/成片/<项目>/03-动画`），
    但 `scripts/` 不能靠数层数找——数错一层就是 `ModuleNotFoundError: motion`。
    这里统一改成「向上找包含 motion.py 的 scripts 目录」。

场景 ID 口径：
    只认 `^s\\d{2}_.*\\.py$`（大小写不敏感），`s01` / `S01` / `s01_valuation_haircut`
    / `scenes/s01_xxx.py` 四种写法都能匹配到同一场。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
SCENE_RE = re.compile(r"^s(\d{2})_.*\.py$", re.IGNORECASE)


def scripts_dir(start: Path | None = None) -> Path:
    """向上找 `<工作区>/管线/scripts`（判据：里面同时有 motion.py）。"""
    base = Path(start or HERE).resolve()
    for cand in [base, *base.parents]:
        d = cand / "scripts"
        if (d / "motion.py").exists():
            return d
    raise RuntimeError(
        "未找到包含 motion.py 的 scripts 目录（起始于 %s）。\n"
        "  检查：这个 03-动画 是不是由 install.py 装出来的？"
        "scripts/ 应该在工作区的 管线/ 下面。" % base)


def ensure_import_path(start: Path | None = None) -> Path:
    """把 03-动画 自己和 scripts/ 放进 sys.path，返回 scripts 目录。"""
    sp = scripts_dir(start)
    for p in (str(sp), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return sp


def scenes_dir(scenes: Path | None = None) -> Path:
    return Path(scenes) if scenes else HERE / "scenes"


def discover_scenes(scenes: Path | None = None) -> list[Path]:
    """列出所有合法场景文件（排除 demo_*.py、_*.py、__init__.py）。"""
    d = scenes_dir(scenes)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.py") if SCENE_RE.match(p.name))


def scene_id(path: Path | str) -> str:
    """s01_valuation_haircut.py -> s01（统一小写）。"""
    m = SCENE_RE.match(Path(path).name)
    return f"s{m.group(1).lower()}" if m else Path(path).stem.lower()


def matches(path: Path | str, keys) -> bool:
    """keys 里任意一项命中就算匹配：s07 / S07 / s07_55cents / scenes/s07_x.py。"""
    p = Path(path)
    stem, sid = p.stem.lower(), scene_id(p)
    for raw in keys:
        k = str(raw).strip().replace("\\", "/")
        if not k:
            continue
        k = Path(k).stem.lower() if k.endswith(".py") else k.lower()
        if k in (stem, sid) or stem.startswith(k):
            return True
    return False


def load_scene(path: Path | str) -> ModuleType:
    """按文件路径加载场景模块（scenes 不是包，不能 import scenes.xxx）。

    同时把场景目录和它的父目录放进 sys.path，保证场景里裸 `import layout` 能过。
    """
    p = Path(path).resolve()
    for d in (str(p.parent), str(p.parent.parent)):
        if d not in sys.path:
            sys.path.insert(0, d)
    name = p.stem
    spec = importlib.util.spec_from_file_location(name, str(p))
    if spec is None or spec.loader is None:
        raise ImportError(f"加载不了场景：{p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def duration(mod: ModuleType, default: float = 10.0) -> float:
    return float(getattr(mod, "DURATION", default))


def resolve_scene(arg: str) -> Path:
    """把一个用户参数（s07 / s07_x / scenes/s07_x.py）解析成存在的文件。"""
    p = Path(arg)
    cands = [p] if p.suffix == ".py" else []
    cands += [HERE / "scenes" / f"{p.stem}.py", HERE / p]
    for c in cands:
        if c.is_file():
            return c.resolve()
    for c in discover_scenes():
        if matches(c, [arg]):
            return c
    raise FileNotFoundError(f"找不到场景：{arg}（场景目录 {HERE / 'scenes'}）")
