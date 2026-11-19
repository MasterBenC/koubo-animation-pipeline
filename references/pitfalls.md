# 坑位清单（全部真实踩过）

> 开工前读一遍。这些坑每一条都花过至少半小时。
> 标 ★ 的是改了架构才解决的，别再退回去。

---

## 渲染

1. **PIL 的 `ImageDraw` 在 RGBA 画布上不混色**，是直接覆盖像素、顺手改 alpha。
   表现：淡入变硬切、空进度条画出来是满的、30% 白的填充变实心、背景网格行上多一条亮线。
   解法：`motion.Canvas` 在**不透明底图上渲染成 RGB**，透明元素统一走 `_comp()` 混。
   场景里不要直接 `c.img.alpha_composite(...)`。

2. **`Image.filter(GaussianBlur)` 会把整张图糊掉**。
   做圆头像羽化时糊了整张卡片，220px 的圆里脸是虚的。
   羽化只能作用在**蒙版的 alpha** 上，不能作用在已经合成好的画面上。

3. **超采样 2x 再缩回**，文字边缘才干净。1x 直接画中文会毛。

4. **每帧都重建大对象会拖慢，但也别乱缓存**。渐变、蒙版、阴影都要缓存（按尺寸做 key），
   缓存后单帧从 ~1.5 s 降到 ~50 ms（20–30 倍）。
   **缓存 key 必须带全所有变量**：羽化量、透明度、fps、底图路径、素材 mtime。
   漏一个就会取到旧图，而且不报错，只是画面"莫名不对"。
   （旧清单里这条被写成第 4、21、22 三条，内容重复，已合并。）

---

## 版式

5. **落边元素不要正好压在边界上**。PIL 抗锯齿溢 1–2px，检查脚本判失败。内缩 4–6px。

6. **头像裁切框按单帧测量必翻车**。人说话会挪 100+ 像素。
   必须扫多个时间点取并集（见 `layout-rules.md` 第二节）。

7. **`to_full` 过渡要传 `1 - prog`**。传 prog 会导致「先缩成圆、最后一帧硬跳全屏」。

8. **场景里的私有辅助函数可能绕过了画布封装**。
   画布改成 RGB 之后，`c.img.alpha_composite()` 和 `dst.getchannel("A")` 这类
   直接操作会崩（`image has wrong mode` / `no channel "A"`）。
   改画布模式后，**所有场景都要跑一遍**才知道哪里炸。

9. **字幕带是禁区**：动画层的字与图形都不进 y 1300–1460。
   人物层（圆头像）在 1415–1695 与带有 45px 视觉重叠是既定设计，后期烧字幕避开 x 700–980。

---

## 时间

10. **不要先写动画再对时间**，一定先列台词表（`cues.json`）再挂元素。

11. **画面静止 6 秒 = 观众划走**。讲重点时画面不能停。
    自查：`audit_timing.py <场次> --thresh 60`（阈值单位是变化像素数），看最后一条事件离结尾多远。

12. **画面领先是 `t + 0.12`，不是 `t - 0.12`**。写反了会让动画整体晚于台词，
    而且不报错，只是"看着别扭"。统一用 `ts = L.lead(t)`。

13. **`-shortest` 会按最短的流剪画面**。给片尾加定格后，音效还是原长度，
    结果 60 帧被剪回 45 帧。**音效长度必须等于总时长**。

14. **音效要跟着画面位移**。定格在开头时，音效整体也要后移，
    否则会出现「画面还没开始、声音先响」。

---

## 工具链

15. **`curl.exe` 在受限沙箱里连不上 HTTPS**（`SEC_E_NO_CREDENTIALS`）。
    出站请求用 Python 的 `urllib`（`vision.py` 就是这么做的）。

16. **PowerShell 的双引号 here-string (`@"..."@`) 会解释反引号转义**：
    - `` `n `` 真换行、`` `t `` 制表符、`` `f `` **换页符**（吃掉后面的 f）、
      `` `a `` **响铃符**（吃掉后面的 a）
    - 写文档时正文里的反引号（Markdown 行内代码）会被误伤，
      典型症状：「final.srt」变「inal.srt」、「ass=」变「ss=」
    - **解法：正文带反引号或多行内容，一律写成 .py 文件落盘，不要在 PowerShell 里拼字符串**
    - 出问题后用 `[c for c in s if ord(c)<32 and c not in "\n\r\t"]` 扫一遍控制字符

17. **写文本只有一个口径：`Path(p).write_text(text, encoding="utf-8")`**。
    - 不传 `encoding` 在 Windows 上按 GBK 写，中文直接乱码/报错；
    - Python 侧**不要**用 `open(..., "w")` 图省事，也别再教 `Set-Content -Encoding UTF8`；
    - 只有 PowerShell 侧必须写文件时，才用
      `[System.IO.File]::WriteAllText($f, $t, (New-Object System.Text.UTF8Encoding($false)))`；
    - `.srt` 例外，用 `utf-8-sig`（剪映/播放器对 BOM 更宽容）；中间件 JSON 一律无 BOM。

18. **OpenCV 5.0 移除了 `CascadeClassifier`，且新 ONNX 导入器读不了 YuNet**
    （`Can't read ONNX file`，ASCII 路径也一样）。另外 **cv2 在中文路径下打不开文件**。
    → `measure_head.py` 不可用，头部标定改**手动网格法**：
    ffmpeg 抽 6–8 帧 → 缩到 540×960 → 叠 120px 网格 → 拼联系表 → 肉眼读头顶/下巴/左右耳
    → 取并集最小框 → 放大 4%（完整步骤见 `layout-rules.md` 第二节）。

19. **`build_clips.py` 的参数是场景编号或文件名主干**（`S07` / `s07` / `s07_55cents` 都行），
    **没有 `--only` flag**。

20. **ffmpeg 的 concat 列表带 BOM 会报 `unknown keyword 'file'`**。
    脚本侧写列表一律 `encoding="utf-8"`。

21. **多个子 agent 同时改同一个文件会互相覆盖**。
    派活前确认目标文件没被占用；同时改同一场景会得到半新半旧的代码。

22. **脚本之间不要靠 `PYTHONPATH` 串路径**。旧文档让人 `PYTHONPATH=某个私人绝对路径`，
    换台机器就全废。现在 `_paths.py` 向上找 `scripts/`，`render_scene.py` 自己把场景目录
    塞进 `sys.path`。写新脚本时用 `_paths.ensure_import_path()`。

---

## 协作

23. **「再大一点」「往下一点」这类反馈，不要靠猜**。
    一次渲染 3 档真图给他选（`pos_options.py` / `size_options.py`）。

24. **子 agent 说「完成了」不等于完成**。必须自己跑一遍验收命令、读一遍静帧。
    有子 agent 在报告阶段崩掉但文件其实已经改好的情况，
    也有改到一半崩掉留下坏文件的情况——都要自己复核。

---

## 素材

25. **照片一律 `contain`，不许裁切**。用户的硬口径是"背景图必须看全"，
    裁掉的图必然返工。

26. **微信临时目录里的 mp4 会被清理**：用户给的 `RWTemp\...` 路径几分钟后就没了。
    真正稳的副本在 `xwechat_files\<user>\msg\video\<yyyy-mm>\<hash>.mp4`。
    **拿到路径先复制进项目**，再开始转写。

27. **人物肖像必须过 vision 复核**。Bing 图片搜索大量串词（返回米老鼠剪纸、蜘蛛侠服装），
    配错人等于"配图即指控"。缺图宁可上 `K.letter_card()`（首字母灰卡）。

28. **vision 单图 >600 KB 或宽 >640 px 会返回 400**；并发最多 2 路，一次一张。
    抽帧后先缩到 560 宽 JPEG 再问。

29. **本机连不上 NYT / Seattle Times / Al Jazeera / NBC / AP / Guardian**（TCP 超时）。
    这些站的截图永远抓不到，别反复试；改用授权转载站并保留出处。

30. **名单类事实最容易写错**（例：七国名单是新加坡、马来西亚、泰国、印度、巴西、南非、挪威，
    不是"东南亚七国"）。逐字抄来源，不要凭印象补全。

31. **`words.json` 的词字段是 `start/end`，不是 `s/e`**。跨片抄转录脚本会 KeyError。

---

## 文字

32. **画面里的字先从"能不能删"问起，但别一次删光**。
    用户先要求删掉所有字（做成了纯图版），下一句就是"太单一"。
    正确做法：只保留标题层（每场一行标题 + 可选副标），别自己加日期/来源/时间码。

33. **柱状图的比例要诚实**。用"涨了 90 倍"讲事，柱子就不能画成 3:1；
    要么真比例，要么别画比例尺、只给数字标签。这条是被 vision 复核抓出来的。

34. **标题层与章节标二选一**。`K.scene_head()` 和 `K.chapter()` 抢同一条带，
    两个都上就是当年"字太多"的复现。

---

## 验收接线（EP.05 新增，全是「脚本没坏、接线错了」）

35. **`check_layout.py` 只认模块级 `bg_frame(t)`** ★。
    场景里把背景在 `frame()` 内部现拼（不放 `bg_frame`），验收脚本拿不到「同一帧的纯背景」，
    只能退回通用渐变底 → 照片底/双色底整帧都是差异 → 19 场能全假失败一遍
    （每场几十万像素"越界"、字幕带 13–17 万像素）。
    正确写法：

    ```python
    def bg_frame(t):
        return K.canvas(t)          # 照片底/双色底在这里 paste + K.dim 自己拼

    def frame(t):
        c = bg_frame(t)
    ```

    新版脚本会在缺 `bg_frame` 且差异 >25% 时打印
    `[!] 本场缺模块级 def bg_frame(t)`，照着提示提出来再跑。

36. **`audit_text_band.py` 要 `motion.text_tracking()`**。
    工作区里若还是旧版 `管线/scripts/motion.py`（EP03/EP04 时期），会
    `AttributeError: module 'motion' has no attribute 'text_tracking'`。
    把 `assets/pipeline/scripts/motion.py` 覆盖过去，旧版留 `.bak_<集名>`。

37. **`audit_timing.py` 读 `02-剪辑/cues.json`**，不是 `文案/cues.json`。
    没复制就 `FileNotFoundError`，别去怀疑脚本。

38. **`check_text.py` 不收 `scenes/s07_xxx.py` 这种带目录的参数**，传 `s07_xxx` 就行；
    而 `check_layout.py` 两种都收。别被前一个的报错带偏。

---

## 响度（EP.05 新增）

39. **`loudnorm` 动态模式在这类口播上稳定欠 0.5–0.7 dB**。
    目标 −14.0，实测 −14.6 ~ −14.9，调 `I=` 也拉不回来（限幅器在削峰）。
40. **源素材峰值高时，线性增益会削波**：源 −18.8 LUFS / TP −3.0 时，+4.8 dB 会把 TP 顶到 **+1.8**。
    这不是「写死增益」的老问题，而是"数学上必然"——必须带限幅：

    ```bash
    -af "volume=6.75dB,alimiter=limit=0.80:attack=4:release=80:level=false"
    ```

41. **`alimiter` 默认 `level=true` 会把输出电平抬回去**：实测成片直接 +0.24 dBTP、−13.47 LUFS。
    `level=false` 不能省。
42. **`limit` 要按编码后的真峰值倒推**：`limit=0.891`（−1.0 dBFS 采样峰）实测成片 TPK 仍是 −0.83；
    `limit=0.80` 才落到 −1.3 左右。AAC 编码后一律复测，别只看中间值。

---

## 素材获取（EP.05 新增）

43. **Cloudflare 验证页会被"截"成一张正常大小的 PNG**。
    页面标题是 `Just a moment...`、`clip.y=0`，图里是验证动画——这种截图必须删掉，不能当信源。
    EP.05 的 Politico probe 与 The Edge Singapore 都是这样废掉的，改用 CNBC / CNBC-TV18。
44. **Playwright 截图最常见的失败是 `waiting for fonts to load` 超时**，不是网络。
    解法：`ctx.route("**/*", abort if resource_type == "font")` + `wait_until="commit"`，
    EP.05 第二轮这么改之后 CNBC 与 CNBC-TV18 一次过。

