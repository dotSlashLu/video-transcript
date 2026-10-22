#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video-transcript — turn any video/audio into a timestamped transcript, fully on-device on macOS.

Channel selection:
  · burned-in subtitles  -> ffmpeg frame sampling + Apple Vision OCR
  · no subtitles         -> Apple SpeechAnalyzer (SpeechTranscriber) on the audio track

Output: <out>/subs.md, <out>/transcript.txt, <out>/meta.json
Stdout: one JSON object (default) or the transcript (`--format text`).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

VERSION = "1.0.0"

CLI_DIR = Path(__file__).resolve().parent
ROOT = CLI_DIR.parent
BIN_DIR = ROOT / ".build"
VOCR = BIN_DIR / "vocr"
TRANSCRIBE = BIN_DIR / "transcribe"
VSUB = CLI_DIR / "vsub.py"
ASRSPLIT = CLI_DIR / "asrsplit.py"
AUTOBAND = CLI_DIR / "autoband.py"

ASR_LOCALE = {"zh-hans": "zh-CN", "zh-hant": "zh-TW", "zh": "zh-CN", "yue": "zh-yue",
              "en": "en-US", "ja": "ja-JP", "ko": "ko-KR", "fr": "fr-FR",
              "de": "de-DE", "es": "es-ES", "it": "it-IT", "pt": "pt-BR"}

EXIT_ARGS, EXIT_RECOGNIZE, EXIT_DEPS = 2, 4, 5


def die(msg, code=EXIT_RECOGNIZE):
    print(f"[video-transcript] {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def slugify(s, n=48):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip()
    return (s[:n] or "video").strip("_")


def check_deps():
    missing = [str(p) for p in (VOCR, TRANSCRIBE) if not p.exists()]
    if missing:
        die("missing compiled binaries: " + ", ".join(missing) +
            "\n  run `make` (or `./setup.sh`) in the repo root first", EXIT_DEPS)
    if not shutil.which("ffmpeg"):
        die("ffmpeg not found. install with: brew install ffmpeg", EXIT_DEPS)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,codec_name", "-of", "json", str(path)])
    try:
        info = json.loads(r.stdout)
    except Exception:
        return {}
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {
        "duration": float((info.get("format") or {}).get("duration") or 0),
        "width": (v or {}).get("width"), "height": (v or {}).get("height"),
        "codec": (v or {}).get("codec_name") or (a or {}).get("codec_name"),
        "has_video": v is not None, "has_audio": a is not None,
    }


def sample_frames(video, dur, work, n=5):
    picks = []
    for i in range(n):
        t = max(0.2, dur * (i / (n + 1) + 0.04))
        f = work / f"probe_{i}.jpg"
        run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-q:v", "2", "-y", str(f)])
        if f.exists():
            picks.append(f)
    return picks


def detect_band(picks, work, langs):
    boxes_out = work / "band_boxes.jsonl"
    with open(boxes_out, "w") as f:
        r = subprocess.run([str(VOCR), "--boxes", "--langs", langs, "--jobs", "5",
                            *[str(p) for p in picks]],
                           stdout=f, stderr=subprocess.DEVNULL, text=True)
    if r.returncode != 0:
        return None
    b = run([sys.executable, str(AUTOBAND), str(boxes_out)])
    try:
        return json.loads(b.stdout.strip().splitlines()[-1])
    except Exception:
        return None


def extract_frames(video, frames_dir, fps):
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    r = run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps}",
             "-q:v", "2", str(frames_dir / "f_%05d.jpg")])
    if r.returncode != 0:
        die("ffmpeg frame extraction failed: " + r.stderr[:300], EXIT_RECOGNIZE)
    return sorted(frames_dir.glob("f_*.jpg"))


def asr_locale(langs, override=None):
    if override:
        return override
    first = langs.split(",")[0].strip()
    key = first.lower()
    return ASR_LOCALE.get(key, first if "-" in first else first + "-US")


def run_ocr(video, out_dir, work, band, fps, langs):
    t0 = time.time()
    frames = extract_frames(video, work / "frames", fps)
    t_frame = time.time() - t0
    # 只有当探测结果"既合理又高命中"时才敢按字幕带裁剪；否则整幅识别，避免裁到错误区域
    crop = None
    if band and band.get("ok") and band.get("hit_rate", 0) >= 0.6:
        crop = band["crop"]
    cmd = [str(VOCR), "--langs", langs, "--jobs", "8"]
    if crop:
        cmd += ["--crop", ",".join(str(x) for x in crop)]
    cmd += [str(p) for p in frames]
    t1 = time.time()
    with open(work / "ocr_raw.jsonl", "w") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, text=True)
    t_ocr = time.time() - t1
    subs = out_dir / "subs.md"
    run([sys.executable, str(VSUB), str(work / "ocr_raw.jsonl"),
         "--out", str(subs), "--fps", str(fps)])
    timing = {"frames": len(frames), "extract_s": round(t_frame, 1),
              "recognize_s": round(t_ocr, 1)}
    return subs, {"crop": crop, "fps": fps}, timing


def run_asr(video, out_dir, work, langs, asr_mode, asr_locale_opt):
    wav = work / "audio.wav"
    r = run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn",
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
    if r.returncode != 0 or not wav.exists():
        die("audio track extraction failed: " + r.stderr[:300], EXIT_RECOGNIZE)
    loc = asr_locale(langs, asr_locale_opt)
    raw = work / "asr_raw.jsonl"
    t0 = time.time()
    with open(raw, "w") as f:
        p = subprocess.run([str(TRANSCRIBE), str(wav), loc, "--mode", asr_mode],
                           stdout=f, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        die("speech recognition failed: " + (p.stderr or "")[-400:], EXIT_RECOGNIZE)
    t_asr = time.time() - t0
    subs = out_dir / "subs.md"
    run([sys.executable, str(ASRSPLIT), str(raw), "--out", str(subs)])
    # 首次运行会下载语音模型，日志里有提示
    timing = {"locale": loc, "mode": asr_mode, "recognize_s": round(t_asr, 1)}
    return subs, {"asr_locale": loc, "asr_mode": asr_mode,
                  "model_installing": "安装模型" in (p.stderr or "")}, timing


def main():
    ap = argparse.ArgumentParser(
        prog="video-transcript",
        description="Transcribe any video/audio on macOS (Vision OCR + SpeechAnalyzer). No API keys, no network for recognition.")
    ap.add_argument("input", help="local video or audio file")
    ap.add_argument("--method", choices=["auto", "ocr", "asr"], default="auto",
                    help="force a channel (default: auto-detect burned-in subtitles)")
    ap.add_argument("--fps", type=float, default=1.0, help="frame sampling rate for OCR (default 1)")
    ap.add_argument("--out", default=None, help="output directory (default ./out/<title>)")
    ap.add_argument("--full", action="store_true", help="OCR the whole frame instead of the subtitle band")
    ap.add_argument("--langs", default="zh-Hans,en-US", help="OCR languages (Vision)")
    ap.add_argument("--asr-mode", choices=["dictation", "transcribe"], default="transcribe",
                    help="dictation = nicer punctuation, ~3x slower")
    ap.add_argument("--asr-locale", default=None, help="force SpeechTranscriber locale, e.g. zh-CN")
    ap.add_argument("--format", choices=["json", "text"], default="json")
    ap.add_argument("--keep-work", action="store_true", help="keep intermediate frames and extracted audio")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--version", action="version", version=f"video-transcript {VERSION}")
    a = ap.parse_args()

    log = (lambda *x: None) if a.quiet else (lambda *x: print(*x, file=sys.stderr))
    check_deps()
    t_start = time.time()
    warnings = []

    work = Path(tempfile.mkdtemp(prefix="video-transcript-"))
    try:
        # ---------- acquire media ----------
        src = a.input
        if re.match(r"^https?://", src):
            die("this tool transcribes local files. Download the media first, "
                "then pass the file path.", EXIT_ARGS)
        video = Path(src).expanduser().resolve()
        if not video.exists():
            die(f"file not found: {video}", EXIT_ARGS)
        title = video.stem

        meta = probe(video)
        dur = meta.get("duration") or 0
        log(f"[video-transcript] {dur:.1f}s {meta.get('width')}x{meta.get('height')} {meta.get('codec')}")
        if not meta.get("has_audio"):
            warnings.append("no audio track: speech recognition unavailable")
        if not meta.get("has_video"):
            warnings.append("audio-only input: channel forced to asr")

        out_dir = Path(a.out).expanduser() if a.out else Path.cwd() / "out" / slugify(title)
        out_dir.mkdir(parents=True, exist_ok=True)

        # ---------- pick channel ----------
        method, band = a.method, None
        if not meta.get("has_video"):
            method = "asr"
        elif not meta.get("has_audio"):
            method = "ocr"
        elif method == "auto":
            log("[video-transcript] probing for burned-in subtitles…")
            picks = sample_frames(video, dur, work, 5)
            band = detect_band(picks, work, a.langs)
            rate = (band or {}).get("hit_rate", 0.0)
            if a.full or (band and band.get("ok") and rate >= 0.6):
                method = "ocr"
            else:
                method = "asr"
                log(f"[video-transcript] subtitle probe: {json.dumps(band, ensure_ascii=False)} "
                    f"-> hit_rate {rate:.0%}, using speech recognition")
        elif method == "ocr" and not a.full:
            picks = sample_frames(video, dur, work, 5)
            band = detect_band(picks, work, a.langs)

        if method == "asr" and not meta.get("has_audio"):
            die("no audio track and no usable subtitles", EXIT_RECOGNIZE)
        log(f"[video-transcript] channel: {method}")

        # ---------- recognize ----------
        if method == "ocr":
            subs, extra, timing = run_ocr(video, out_dir, work, band, a.fps, a.langs)
        else:
            subs, extra, timing = run_asr(video, out_dir, work, a.langs, a.asr_mode, a.asr_locale)

        transcript = out_dir / "transcript.txt"
        plain = Path(str(subs) + ".plain.txt")
        if plain.exists():
            plain.replace(transcript)

        if method == "asr":
            warnings.append("ASR mis-hears numbers and homophones (e.g. 一万->1000, 21%->2十一); "
                            "verify any figure before quoting it")

        text = subs.read_text(encoding="utf-8") if subs.exists() else ""
        lines = [l for l in text.strip().splitlines() if l.strip()]
        bodies = {l.split("] ", 1)[-1].strip() for l in lines}
        diversity = round(len(bodies) / max(1, len(lines)), 3)
        chars = len(transcript.read_text(encoding="utf-8")) if transcript.exists() else 0
        # 每秒产出字数：正常口播/字幕 3~5 字/秒；若远低于此，说明识别到的只是固定字
        cps = round(chars / dur, 2) if dur > 0 else 0.0

        if method == "ocr" and dur >= 20 and cps < 1.5:
            warnings.append(
                f"OCR output density is very low ({cps} chars/s, {chars} chars over {dur:.0f}s); "
                f"the video probably has no real subtitles — retry with --method asr")
        elif method == "ocr" and len(lines) >= 8 and diversity < 0.25:
            warnings.append(
                f"OCR output is repetitive ({len(bodies)} unique lines of {len(lines)}); "
                f"retry with --method asr if the result looks like watermarks")

        result = {
            "ok": True,
            "method": method,
            "title": title,
            "source": src,
            "duration_s": round(dur, 1),
            "out_dir": str(out_dir),
            "subs": str(subs),
            "transcript": str(transcript),
            "segments": len(lines),
            "unique_segments": len(bodies),
            "diversity": diversity,
            "chars": chars,
            "chars_per_sec": cps,
            "detection": band,
            **extra,
            "timing": {**timing, "total_s": round(time.time() - t_start, 1)},
            "warnings": warnings,
        }
        (out_dir / "meta.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        if a.format == "text":
            print(text)
        else:
            print(json.dumps(result, ensure_ascii=False))
    finally:
        if a.keep_work:
            print(f"[video-transcript] work dir kept: {work}", file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
