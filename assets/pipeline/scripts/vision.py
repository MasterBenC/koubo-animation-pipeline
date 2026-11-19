#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""视觉问答：把本地图片发给多模态模型，拿回一句人话判断。

用途：渲染完自己看帧（遮挡 / 出框 / 构图 / 接缝），不依赖人眼复检。
图片只发这一张（base64 data URI），不发原片、不发音频。

配置全部走环境变量（没有任何写死的绝对路径）：

    VISION_API_KEY    必填；没设就回退 OPENAI_API_KEY；都没有就报错退出
    VISION_BASE_URL   可选，默认 https://api.openai.com/v1
    VISION_MODEL      可选，默认 gpt-4o-mini
    VISION_CONFIG     可选，指向一个 KEY=VALUE 的文本文件（一次配好，长期用）

示例（PowerShell，会话内临时设置）：
    $env:VISION_API_KEY="sk-..."
    $env:VISION_BASE_URL="https://api.openai.com/v1"
    $env:VISION_MODEL="gpt-4o-mini"

用法:
    python vision.py 图1.png [图2.png ...] -p "这张图里有什么问题？"
    python vision.py shot.png -p "人物有没有被右下角的圆头像挡住？" --max-tokens 200
    python vision.py a.png -p "..." --raw        # 连思考过程一起打印
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


def load_cfg(config_file: str | None = None) -> dict:
    """环境变量 + 可选配置文件；缺 key 直接报错退出（不猜、不读私人路径）。"""
    cfg: dict[str, str] = {}
    path = config_file or os.environ.get("VISION_CONFIG")
    if path:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"VISION_CONFIG 指向的文件不存在：{p}")
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip().upper()] = v.strip()

    def pick(*names: str) -> str:
        for n in names:
            v = os.environ.get(n) or cfg.get(n)
            if v:
                return v
        return ""

    key = pick("VISION_API_KEY", "OPENAI_API_KEY")
    if not key:
        raise SystemExit(
            "缺少 API key：请设置环境变量 VISION_API_KEY（或 OPENAI_API_KEY）。\n"
            "  临时：$env:VISION_API_KEY=\"sk-...\"\n"
            "  长期：把 KEY=VALUE 写进一个文件，再设 VISION_CONFIG=<那个文件>")
    return {
        "api_key": key,
        "base_url": (pick("VISION_BASE_URL", "OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        "model": pick("VISION_MODEL") or DEFAULT_MODEL,
    }


def ask(images: list[Path], prompt: str, max_tokens: int = 400,
        model: str | None = None, timeout: int = 180,
        config_file: str | None = None) -> dict:
    cfg = load_cfg(config_file)
    model = model or cfg["model"]

    content = [{"type": "text", "text": prompt}]
    for p in images:
        p = Path(p)
        mime = mimetypes.guess_type(str(p))[0] or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    body = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens, "temperature": 0.2}
    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + cfg["api_key"],
                 "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    msg = d["choices"][0]["message"]
    return {"text": (msg.get("content") or "").strip(),
            "reasoning": (msg.get("reasoning_content") or "").strip(),
            "usage": d.get("usage", {})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("-p", "--prompt", required=True)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--model", default=None)
    ap.add_argument("--config", default=None, help="KEY=VALUE 配置文件（也可用 VISION_CONFIG）")
    ap.add_argument("--raw", action="store_true", help="同时打印思考过程")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    imgs = [Path(p) for p in args.images]
    for p in imgs:
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            return 2
    try:
        res = ask(imgs, args.prompt, args.max_tokens, args.model, config_file=args.config)
    except SystemExit:
        raise
    except Exception as e:
        print(f"vision failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print(res["text"])
    if args.raw and res["reasoning"]:
        print("\n--- reasoning ---\n" + res["reasoning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
