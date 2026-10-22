#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""asrsplit.py — 把 transcribe 的字级结果切成句级时间轴
输入: transcribe 输出的 jsonl（每行含 runs=[{s,e,t}]）
输出: [MM:SS] 句子    并同时写 <out>.plain.txt
用法: asrsplit.py full.jsonl [--out subs.md] [--maxlen 30]
"""
import json, sys, argparse

END_PUNCT = "。？！?!；;"
SOFT_PUNCT = "，,、：:"
ALL_PUNCT = END_PUNCT + SOFT_PUNCT


def fmt(s):
    m, sec = divmod(int(round(s)), 60)
    return f"{m:02d}:{sec:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--maxlen", type=int, default=30,
                    help="句子理想长度；遇逗号且超过则断，超过 1.5 倍无条件断")
    a = ap.parse_args()

    sentences = []
    for line in open(a.jsonl, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        buf, s0, e0 = "", None, None
        prev_e = None
        for r in d.get("runs") or []:
            piece = (r.get("t") or "").strip()
            gap = (r["s"] - prev_e) if prev_e is not None else 0.0
            prev_e = r["e"]
            if not piece:
                continue
            if s0 is None:
                s0 = r["s"]
            buf += piece
            e0 = r["e"]
            hard = any(p in piece for p in END_PUNCT)
            soft = any(p in piece for p in SOFT_PUNCT) and len(buf) >= a.maxlen
            # 无标点时的兜底：只在极端长度才切，避免把词切碎（ASR 字级时间戳无停顿信息）
            forced = len(buf) >= a.maxlen * 4
            if hard or soft or forced:
                sentences.append((s0, e0, buf))
                buf, s0 = "", None
        if buf.strip():
            sentences.append((s0 if s0 is not None else d["start"],
                              e0 if e0 is not None else d["end"], buf))

    # 以标点开头的句子：把标点并回上一句
    fixed = []
    for s, e, t in sentences:
        if fixed and t and t[0] in ALL_PUNCT:
            ps, pe, pt = fixed[-1]
            fixed[-1] = (ps, e, pt + t[0])
            t = t[1:]
            if not t.strip():
                continue
        fixed.append((s, e, t))

    lines = [f"[{fmt(s)}] {t}" for s, e, t in fixed]
    text = "\n".join(lines)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
        open(a.out + ".plain.txt", "w", encoding="utf-8").write(
            "".join(t for _, _, t in fixed))
    print(text)
    print(f"# {len(fixed)} 句", file=sys.stderr)


if __name__ == "__main__":
    main()
