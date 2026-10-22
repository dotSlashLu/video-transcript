---
name: video-transcript
description: Transcribe a local video or audio file on macOS using Apple's own engines — Vision OCR reads burned-in subtitles, SpeechAnalyzer transcribes speech. No API keys, no uploads, no per-minute cost. Takes a file path, not a URL. Use when asked to transcribe, quote or summarize a video or audio file already on this machine.
---

# Video → transcript

A 7-minute 1080p file becomes 2,000 characters of timestamped text in **10–30 seconds**, entirely on this Mac. The value is not raw transcription — it is being able to *reason about* a video: quote it, check it, summarize it.

**This tool works on files.** It does not fetch anything from the network. If what you have is a link, obtain the media file first, then point this tool at it.

## Install (first run only)

```bash
git clone https://github.com/dotSlashLu/video-transcript.git   # anywhere you keep tools
cd video-transcript
./install.sh --json --skill-dir <your-skills-dir>/video-transcript
```

The installer copies the runtime into `~/.local/share/video-transcript` and writes a `video-transcript`
launcher into `~/.local/bin` (it warns if that directory is not on your PATH). The clone is
disposable afterwards.

Read the JSON. If `ready` is false:

- every entry in `needs_user` carries a `command` — run it yourself, except when it needs sudo or a GUI (`xcode-select --install` opens a dialog: hand that one to the user);
- rerun `./install.sh --json` until `ready` is true.

Exit codes: 0 = ready, 1 = blocked on you, 2 = installer failure. The installer is idempotent; running it again is always safe.

## Run

```bash
video-transcript <file>
```

| Situation | Command |
|---|---|
| Default | `video-transcript ~/Movies/lecture.mp4` |
| You know it has burned-in subtitles | add `--method ocr` |
| You know it is speech only | add `--method asr` |
| Slides / screen recording, text everywhere | `--method ocr --full` |
| Need nicer punctuation more than speed | `--asr-mode dictation` (≈3× slower) |
| Chinese variety | `--asr-locale zh-TW` / `zh-HK` / `yue-CN` |
| Want the text on stdout, not JSON | `--format text` |

`auto` samples 5 frames, OCRs them, discards text that repeats across frames (watermarks), and picks OCR only if ≥60% of frames still show text in the lower third. If that guess disappoints you, override it — the flag always wins.

## Read the result, don't just take it

stdout is one JSON object. Fields that decide what you do next:

| Field | Meaning |
|---|---|
| `method` | `ocr` or `asr` — which channel actually ran |
| `subs` / `transcript` | timestamped file / plain text file |
| `chars`, `chars_per_sec` | volume sanity: normal speech is 3–5 chars/s |
| `warnings` | **read these before trusting anything** |
| `detection` | subtitle probe detail (hit rate, watermarks found) |

Act on warnings, don't just report them:

- `low density ... retry with --method asr` → an OCR run found almost nothing. Rerun with `--method asr`.
- `ASR mis-hears numbers and homophones` → this run is speech-only. See "Numbers" below.
- `no audio track` → OCR is the only option; ASR will fail.

If `subs` came out empty or as one line repeating for the whole file, the channel was wrong. Rerun with the other method.

## Numbers are the failure mode

ASR hears **一万 → 1000**, **21% → 2十一**, **2048亿 → 20048亿**, **重仓 → 中餐**, **先赞后看 → 先站后看**. Homophones are harmless for summarizing; **numbers are not**, because a wrong figure silently changes the conclusion.

Rules:

1. Prefer the OCR channel for anything financial, medical or numeric — subtitles are text the author wrote, ASR is a guess.
2. If you only have ASR, cross-check every figure that will appear in your summary against `subs.md` timestamps, or mark it `≈`.
3. Never silently "fix" a number you cannot verify. Write `（≈，原文为 20048亿，疑为 2048亿）` and let the reader decide.

## Summarizing method

Do not paste the transcript back. Build a skeleton first, then write prose over it.

1. **Segment by time.** Use timestamps to cut the talk into 3–6 movements. This keeps structure the speaker actually intended.
2. **Extract the spine**: for each movement, one *claim* + the *evidence* used + the *conclusion drawn*. Claims without evidence are opinions — label them as such.
3. **Separate fact from opinion.** Figures, dates, named events are facts (and must survive the number check). Forecasts, analogies, judgments are the speaker's views — attribute them ("作者认为…"), never adopt them as the answer.
4. **Keep the reasoning, drop the filler.** "老规矩先赞后看", channel plugs, repetitions — delete. An idea that appears once but carries the argument — keep.
5. **Flag what breaks it.** Most finance/tech talks have one load-bearing assumption. Name it, and say what would falsify it. This is worth more than a longer summary.
6. **Quote with timestamps** for anything you would be challenged on: `（04:53）`.

Aim for: one-paragraph verdict, the spine as sections, a short "what would change my mind" block. Not a chronological retelling.

## Output

The transcript is a working artifact, not the deliverable. Unless the user asked for the raw text:

- write the summary where the user expects it (a `summary.md` next to `subs.md` is a good default),
- keep `subs.md` around so any claim can be traced back to a timestamp,
- if the topic has lasting value and the user keeps a knowledge base, offer to file it — once, don't insist.

## Failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `this tool transcribes local files` | a URL was passed | download the media first, then pass the path |
| `file not found` | wrong path, or `~` not expanded | use an absolute path |
| `missing compiled binaries` | `make` / `install.sh` never ran | rerun `./install.sh --json` |
| ASR returns nothing | no speech, or wrong locale | `--asr-locale`, or `--method ocr` |
| OCR text includes watermarks | watermark inside the subtitle band | harmless for summarizing — the model ignores repeated lines; the probe already strips them for channel selection |
| Video is a lecture with slides | text fills the frame | `--method ocr --full` |
| DRM video (Netflix etc.) | stream is not extractable | not supported |

See `references/architecture.md` for how the channels work internally.
