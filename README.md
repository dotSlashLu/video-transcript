# video-transcript

**Turn any video into timestamped text — on-device, on macOS, for free.**

English · [简体中文](README.zh-CN.md)

Give it a Xiaohongshu link, a YouTube file, a screen recording, or a podcast episode. It gives back a transcript you can quote, search and summarize — without uploading a single byte, without an API key, and without paying per minute.

- **Two channels, picked automatically.** Burned-in subtitles → Apple Vision OCR. No subtitles → Apple SpeechAnalyzer.
- **10–30 seconds for a 7-minute video.** No GPU rental, no queue.
- **Built for agents.** One JSON object on stdout, stable fields, actionable warnings.

```
7:12 video  →  OCR channel  →  242 subtitle segments, 2,093 chars  →  27 s
            →  ASR channel  →  60 sentences, 2,238 chars           →  8.6 s
```

---

## 🤖 For agents — install it yourself

Paste this into any agent with shell access (Claude Code, Codex, Cursor…):

> Install `video-transcript` from `https://github.com/dotSlashLu/video-transcript`. Clone it wherever
> you keep tools, then do three things:
>
> 1. **Dependencies + build** — `./install.sh --json`, and resolve every entry in `needs_user`
>    (ask me before running anything that needs sudo). Rerun until `ready` is true.
> 2. **Make the CLI resolvable** — the installer copies the runtime to `~/.local/share/video-transcript`
>    and writes a `video-transcript` launcher to `~/.local/bin` (override with `--prefix` / `--bin-dir`).
>    Make sure that bin directory is on your PATH.
> 3. **Install the skill for yourself** — `./install.sh --skill-dir <your-skills-dir>/video-transcript`,
>    pointing at the directory you actually load skills from.
>
> Finish by running `./video-transcript <a sample link or file>` and reporting its `method`, `chars` and `warnings`.

All three in one line (fill in your own skills directory):

```bash
git clone https://github.com/dotSlashLu/video-transcript.git && cd video-transcript \
  && ./install.sh --yes --skill-dir "<your-skills-dir>/video-transcript"
```

`install.sh` is idempotent, needs no input, and prints exactly **one JSON object** on stdout (progress goes to stderr). It separates what it fixed from what only you can do:

```json
{
  "ready": false,
  "checks": [{"name": "ffmpeg", "status": "missing", "detail": "not installed"}],
  "fixed": [],
  "needs_user": [
    {"issue": "Xcode Command Line Tools are required to compile the recognizers",
     "command": "xcode-select --install"}
  ],
  "next": "resolve needs_user, then rerun ./install.sh --json"
}
```

| exit | meaning |
|---|---|
| 0 | ready — `./video-transcript <input>` works |
| 1 | blocked on `needs_user` |
| 2 | installer itself failed |

Notes for agents: `xcode-select --install` opens a GUI prompt, so hand that one to the user; `brew install ffmpeg` you can run yourself (or pass `--yes`). Node is optional — only used to resolve media from web pages.

---

## Why this exists

Feeding 432 frames to a vision model works, but it is slow and expensive, and 90% of those frames are decorative animation. A talking-head explainer has two things worth reading: the **subtitles the author typed** (high-quality, already proof-read text) and the **speech**. Everything else is wallpaper.

So the tool does the cheap, precise thing: sample frames, read only the subtitle band with the OCR engine built into macOS, and merge duplicates. When there are no subtitles, it falls back to the speech engine built into macOS. Both run on the Neural Engine, both cost zero.

## Requirements

| | |
|---|---|
| OS | macOS 26+ (SpeechAnalyzer). OCR alone works on older versions. |
| Toolchain | Xcode Command Line Tools (`swiftc`) |
| Runtime | `ffmpeg`, `python3`, `node` (node only for fetching web pages) |

```bash
./install.sh           # checks deps, compiles, copies the runtime out of the repo
./install.sh --json    # same thing, machine-readable
./install.sh --prefix <dir> --bin-dir <dir>   # install somewhere else
make doctor            # which speech languages this Mac supports / has installed
```

The runtime (`cli/` + `.build/`) lands in `~/.local/share/video-transcript` and a `video-transcript`
launcher in `~/.local/bin`. **The clone is disposable once this finishes** — and a later
`git pull` cannot silently change what is installed.

```text
```

First run in a new language downloads that speech model once (a few seconds). After that it is fully offline.

## Usage

```bash
# a web page (uses your logged-in Chrome to resolve the media URL)
video-transcript "https://xhslink.cn/o/8p8U68Y44ib"

# a local file
video-transcript ~/Movies/lecture.mp4

# audio only
video-transcript ~/Downloads/podcast.m4a

# force a channel
video-transcript video.mp4 --method asr
video-transcript slides.mp4 --method ocr --full
```

Outputs land in `out/<title>/`:

| File | Content |
|---|---|
| `subs.md` | timestamped lines, `[MM:SS] text` |
| `transcript.txt` | plain text |
| `meta.json` | channel, detection detail, timing, warnings |

### CLI

```
video-transcript <input> [--method auto|ocr|asr] [--fps 1] [--out DIR] [--full]
    [--langs zh-Hans,en-US] [--asr-mode transcribe|dictation]
    [--asr-locale zh-CN] [--format json|text] [--keep-work] [--quiet]
```

`--method auto` (default) is a real decision, not a guess by name: it samples 5 frames, OCRs the lower third, drops anything that repeats across frames (watermarks, channel logos), and switches to ASR unless ≥60% of frames still show text. Any explicit `--method` overrides it.

### JSON contract

```json
{
  "ok": true,
  "method": "ocr",
  "title": "…",
  "duration_s": 432.4,
  "subs": "out/…/subs.md",
  "transcript": "out/…/transcript.txt",
  "segments": 242,
  "chars": 2093,
  "chars_per_sec": 4.84,
  "detection": {"hit_rate": 1.0, "watermarks": [], "crop": [0, 0.894, 1, 0.08]},
  "timing": {"extract_s": 5.7, "recognize_s": 19.5, "total_s": 27.2},
  "warnings": []
}
```

`warnings` is the part that matters. Examples:

- `OCR output density is very low (0.23 chars/s …) — retry with --method asr` → the run scanned a watermark, not subtitles.
- `ASR mis-hears numbers and homophones …` → verify every figure before quoting.

## Measured numbers

M-series Mac, macOS 27, one 432-second 1080p Chinese explainer:

| | OCR channel | ASR channel |
|---|---|---|
| Channel probe | 5 frames, 0.3 s | — |
| Frames / audio | 432 frames, 5.7 s | 16 kHz mono, 0.8 s |
| Recognition | 19.5 s (45 ms/frame, 8-way parallel) | **6.8 s** (≈60× realtime) |
| Output | 242 segments / 2,093 chars | 60 sentences / 2,238 chars |
| **Total** | **27 s** | **8.6 s** |

Accuracy, against the author's own subtitles as reference:

| Engine | Similarity | Notes |
|---|---|---|
| Vision OCR | — | 1–3 near-miss characters per 1,000 |
| `SpeechTranscriber` | 0.963 (CER ≈5.8%) | fast, terse punctuation |
| `DictationTranscriber` | 0.930 (CER ≈10.1%) | nicer punctuation, 3× slower |

ASR sometimes looks *worse* than it is: it restores spoken words the subtitles trimmed ("说白了", "你看", "群聊红包小程序"). Those count as errors in CER but are more faithful to what was said.

## Agent integration

`skill/` is the methodology an agent should follow: how to choose a channel, how to read the JSON, how to handle the number problem, and how to turn a transcript into a summary that separates the speaker's claims from facts. Point your agent at the repo root and it should be able to run the tool without further instructions.

Install it as a skill: `./install.sh --skill-dir <your-skills-dir>/video-transcript`, or for Shrimp: `shrimp skill install <repo>/skill`.

## Design notes

- **Only the subtitle band is OCR'd.** Whole-frame OCR picks up decorative text and is measurably less accurate; cropping to the band fixed 风量 → 尽量 on the same frame.
- **1 fps, not more.** Subtitles stay 2–4 s. Higher rates only capture the "typewriter" intermediate states and inject garbage.
- **Merging by similarity, not equality.** Word-by-word animation produces variants of the same line ("开了一家" / "开了—家"); `difflib` ≥0.82 merges them and a majority vote picks the spelling.
- **Watermarks are stripped for the channel decision, never from the text.** Removing them from output is pointless — a summarizer ignores a line that repeats forever — but leaving them in the *probe* makes subtitle-less videos look subtitled.
- **Media fetching goes through the user's Chrome.** Xiaohongshu, WeChat and friends need a real session; static scraping gets a login wall. Signed URLs expire in minutes, so download immediately.

## Limitations

- Speech numbers and proper nouns are unreliable (see `warnings`). Verify before quoting.
- Graphics, charts and on-screen figures are not read. Use `--full`, or ask a vision model about specific frames.
- No subtitles **and** no audio → nothing to extract.
- DRM streams (Netflix, Disney+) are out of scope; `blob:` MSE sources cannot be resolved.
- Speech models must exist for the language; `make doctor` shows what is installed.
- Visual/live-action videos with stylized subtitles OCR worse than clean explainer typography.

## Repository layout

```
install.sh           agent-runnable installer (idempotent, --json, --yes, --prefix, --skill-dir)
video-transcript     entry point — ./video-transcript <url|file>
cli/video_transcript.py          orchestrator: acquire → probe → channel → recognize → report
cli/vocr.swift       Vision OCR CLI (batch, parallel, crop, scale, bbox output)
cli/transcribe.swift SpeechAnalyzer transcription (transcribe | dictation)
cli/autoband.py      subtitle-band probe + watermark rejection
cli/vsub.py          frame OCR → subtitle segments (similarity merge, majority vote)
cli/asrsplit.py      word-level ASR → sentence timeline
cli/fetch_video.mjs  resolve media URLs through Chrome DevTools Protocol
cli/probe_speech.swift  diagnostic: supported / installed speech locales
skill/SKILL.md       agent methodology (installable skill folder)
```

## License

MIT
