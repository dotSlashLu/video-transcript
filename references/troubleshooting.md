# Troubleshooting

## Build

**`missing compiled binaries: .build/vocr`**
Run `make` in the repo root. `setup.sh` does the same thing with dependency checks.

**`xcrun: error: invalid active developer path`**
`xcode-select --install`.

**Swift compile fails on `SpeechTranscriber`**
That API needs macOS 26+ SDK. OCR (`vocr.swift`) compiles on much older SDKs — you can build only that target with `make .build/vocr`.

## Channel selection

**A video with subtitles went to ASR.**
The probe requires ≥60% of sampled frames to contain non-watermark text in the lower 30%. Check `meta.json → detection.hit_rate`. Causes: subtitles in the upper half, subtitles smaller than 3 characters per block, or a subtitle line that repeats across samples and got classified as a watermark. Force with `--method ocr`.

**A video without subtitles went to OCR.**
`detection.hit_rate` will be high. Usually a persistent lower-third banner or a chart in the bottom area. The result will carry the warning `OCR output density is very low` — rerun with `--method asr`.

**Watermark text appears in the transcript.**
Expected and harmless: the probe strips watermarks only for channel selection, not from output. A summarizer ignores a line that repeats across the whole file. If you want it gone from the artefacts, crop the band manually with `--full` off and inspect `detection.watermarks`.

## Fetching

**`could not resolve media from page`**
The page is not a video page, requires login, or the CDP proxy is not running. Open the page in the user's own Chrome first; the tool reuses that session. Check the proxy with `curl -s http://localhost:3456/targets`.

**`media download failed (login/cookie required?)`**
Xiaohongshu URLs carry `sign`/`t` parameters that expire in minutes. Rerun the command rather than reusing an old URL.

**Only `blob:` sources are listed.**
The player uses MSE segments with no single file. Not supported — sample frames via screenshots instead.

## Recognition

**ASR returns an empty transcript.**
No speech, or wrong locale. Check `make doctor`; try `--asr-locale zh-TW`, `zh-HK`, `yue-CN`, or `en-US`.

**ASR output has no punctuation.**
`SpeechTranscriber` punctuation is sparse on long monologues. Use `--asr-mode dictation` (≈3× slower, better punctuation).

**Numbers are wrong.**
Known and expected. See the number rules in `SKILL.md`. The only real fix is the OCR channel or manual verification against the source.

**OCR reads 风量 instead of 尽量.**
Near-miss characters happen; cropping to the band (default) already improves accuracy a lot. For stubborn lines try `--scale` on `vocr` directly, or `--full`.

**Transcript stops halfway.**
Check `duration_s` against the real duration. A truncated download gives a truncated transcript; rerun.

## Performance

**Recognition is much slower than the numbers in the README.**
First call in a fresh process loads the Vision model (~28 s). Then check that `--jobs` is at least 6 and that you are not running OCR and ASR simultaneously.

**Disk fills up.**
Frames are written to a temp dir and deleted on exit. Use `--keep-work` only when debugging, and clear `out/` periodically.
