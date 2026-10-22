#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autoband.py — 从抽样帧里判断"是否有硬字幕"，并给出字幕带裁剪区域。

读 vocr --boxes 的输出（每帧若干文本行 + 归一化 bbox，Vision 坐标系原点左下角）。

判断方法：
  1. 只看画面下部（Vision y < --lower）且长度 >= --min-chars 的文本块；
  2. 跨帧重复出现的同一文本（出现在 >= 60% 的帧里）判为水印/台标，剔除；
  3. 剔除后仍有文本的帧记一次命中，命中率 = 命中帧 / 总帧数；
  4. 字幕带 = 剩余文本块上边界的 10% 分位 ~ 下边界的 90% 分位，外加边距。
输出 JSON: {"ok","crop","frames","hit_frames","watermarks","reason"}
"""
import json, sys, argparse
from collections import Counter
from difflib import SequenceMatcher


def similar(a, b, th=0.75):
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 3:
        return False
    return SequenceMatcher(None, short, long_).ratio() >= th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--lower", type=float, default=0.30,
                    help="只考虑 Vision y 小于该值的块（画面下部）")
    ap.add_argument("--max-h", type=float, default=0.45, help="推断区域超过该高度则视为不可用")
    ap.add_argument("--pad", type=float, default=0.015)
    ap.add_argument("--min-chars", type=int, default=3)
    ap.add_argument("--repeat", type=float, default=0.6,
                    help="同一文本出现在该比例的帧中即判为水印")
    a = ap.parse_args()

    frames_boxes = []
    for line in open(a.jsonl, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        kept = []
        for b in d.get("boxes") or []:
            if b["y"] >= a.lower:
                continue
            if len(b["text"].strip()) < a.min_chars:
                continue
            kept.append(b)
        frames_boxes.append(kept)

    n = len(frames_boxes)
    if n == 0:
        print(json.dumps({"ok": False, "reason": "无输入帧", "frames": 0, "hit_frames": 0}))
        return

    # 跨帧重复出现的文本 = 水印/台标（OCR 每帧可能识别成略有差异的变体，故用模糊匹配）
    frame_texts = [[b["text"].strip() for b in boxes] for boxes in frames_boxes]
    need = max(2, int(round(a.repeat * n)))
    watermarks = set()
    for texts in frame_texts:
        for t in texts:
            hits = sum(1 for other in frame_texts if any(similar(t, s) for s in other))
            if hits >= need:
                watermarks.add(t)

    tops, bots, hit_frames = [], [], 0
    for boxes in frames_boxes:
        kept = [b for b in boxes
                if not any(similar(b["text"].strip(), w) for w in watermarks)]
        if not kept:
            continue
        hit_frames += 1
        for b in kept:
            tops.append(1.0 - (b["y"] + b["h"]))   # 距图像顶部
            bots.append(1.0 - b["y"])

    watermarks = sorted(watermarks)

    if not tops:
        print(json.dumps({"ok": False, "reason": "下部无稳定文本", "frames": n,
                          "hit_frames": 0, "watermarks": watermarks[:5]}))
        return

    tops.sort(); bots.sort()
    top = max(0.0, tops[len(tops) // 10] - a.pad)
    bot = min(1.0, bots[len(bots) * 9 // 10] + a.pad)
    h = bot - top
    ok = 0.02 <= h <= a.max_h
    print(json.dumps({
        "ok": ok,
        "crop": [0.0, round(top, 4), 1.0, round(h, 4)],
        "frames": n,
        "hit_frames": hit_frames,
        "hit_rate": round(hit_frames / n, 3),
        "watermarks": watermarks[:5],
        "blocks": len(tops),
        "reason": "" if ok else f"字幕带高度 {h:.2f} 不合理",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
