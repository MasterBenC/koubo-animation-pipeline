#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""视觉问答：把本地图片发给多模态模型，拿回一句人话判断。

用途：渲染完自己看帧（遮挡 / 出框 / 构图 / 接缝），不依赖人眼复检。
图片只发这一张（base64 data URI），不发原片、不发音频。

用法:
    python vision.py 图1.png [图2.png ...] -p "这张图里有什么问题？"
    python vision.py shot.png -p "人物有没有被右下角的画中画挡住？" --max-tokens 200
    python vision.py a.png -p "..." --raw        # 连思考过程一起打印
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
import urllib.request
from pathlib import Path

API_FILE = Path(r"C:\Users\benhu\Desktop\档案001\api.txt")


def load_cfg(path: Path = API_FILE) -> dict:
    cfg = {}
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    cfg.setdefault("model", "qwen3.8-omni-flash")
    return cfg


def ask(images: list[Path], prompt: str, max_tokens: int = 400,
        model: str | None = None, timeout: int = 180) -> dict:
    cfg = load_cfg()
    base = cfg["base_url"].rstrip("/")
    key = cfg["api_key"]
    model = model or cfg.get("model") or "qwen3.8-omni-flash"

    content = [{"type": "text", "text": prompt}]
    for p in images:
        p = Path(p)
        mime = mimetypes.guess_type(str(p))[0] or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    body = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens, "temperature": 0.2}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0"},
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
    ap.add_argument("--raw", action="store_true", help="同时打印思考过程")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    imgs = [Path(p) for p in args.images]
    for p in imgs:
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            return 2
    try:
        res = ask(imgs, args.prompt, args.max_tokens, args.model)
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
