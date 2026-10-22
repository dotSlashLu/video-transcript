#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 vocr 的逐帧结果合并成带时间轴的字幕序列。
用法: vsub.py build/ocr_raw.jsonl [--fps 1] [--out subs.md]
输入行: {"file":"media/frames/f_0001.jpg","lines":["..."]}
"""
import json, re, sys, argparse

def norm(s):
    return re.sub(r'\s+', '', s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fps", type=float, default=1.0)
    a = ap.parse_args()

    rows = []
    for line in open(a.jsonl, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        m = re.search(r'(\d+)\.(?:jpg|png|jpeg)$', d["file"])
        idx = int(m.group(1)) if m else len(rows) + 1
        text = "".join(d.get("lines") or []).strip()
        rows.append((idx, text))
    rows.sort()

    # 合并连续相同/近似文本 -> 段（字幕常有逐字出现、OCR 形近字抖动，用相似度归并）
    import difflib
    from collections import Counter

    def similar(a, b):
        a, b = norm(a), norm(b)
        if not a or not b:
            return False
        if a == b:
            return True
        if min(len(a), len(b)) <= 4:
            return False
        if a in b or b in a:
            return True
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.82

    segs = []
    for idx, text in rows:
        t = (idx - 1) / a.fps            # 帧对应的秒数（第一帧=0s）
        if not text:
            continue
        if segs and similar(segs[-1]["cands"].most_common(1)[0][0], text):
            segs[-1]["end"] = t + 1.0 / a.fps
            segs[-1]["cands"][text] += 1
        else:
            segs.append({"start": t, "end": t + 1.0 / a.fps,
                         "cands": Counter({text: 1})})

    for s in segs:
        # 多数票选文字；平票取更长
        s["text"] = sorted(s["cands"].items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]

    # 丢掉极短噪声（只出现在 1 帧、且前后不同）
    def fmt(s):
        m, sec = divmod(int(round(s)), 60)
        return f"{m:02d}:{sec:02d}"

    out = []
    for s in segs:
        out.append(f"[{fmt(s['start'])}] {s['text']}")
    text = "\n".join(out)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
    print(f"# {len(rows)} 帧 -> {len(segs)} 条字幕段", file=sys.stderr)
    print(text)
    # 压缩纯文本（给总结用）
    plain = "".join(s["text"] for s in segs)
    open((a.out or a.jsonl) + ".plain.txt", "w", encoding="utf-8").write(plain)
    print(f"# 纯文本 {len(plain)} 字 -> {(a.out or a.jsonl)}.plain.txt", file=sys.stderr)

if __name__ == "__main__":
    main()
