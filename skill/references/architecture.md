# How it works

## Data flow

```
input: local video / audio file ────────────▶ temp working dir
                                                        │
                                            ffprobe ────┤ has video? has audio? duration?
                                                        │
                        ┌───────────────────────────────┴──────────────────────────┐
                        │ channel decision                                          │
                        │                                                           │
             no video stream                                  video stream present  │
                        │                                                   │       │
                        ▼                                          sample 5 frames   │
                    (always ASR)                                            │       │
                                                                            ▼       │
                                                          vocr --boxes (full frame) │
                                                                            │       │
                                                          autoband.py: lower third  │
                                                          - drop cross-frame dupes  │
                                                          - hit_rate = frames w/ text
                                                        ┌───────────────────────────┤
                                      hit_rate ≥ 0.6    │            hit_rate < 0.6 │
                                                        ▼                           ▼
                                              OCR channel                    ASR channel
                                    432 frames @ 1 fps              extract 16 kHz mono
                                    vocr --crop band                 transcribe.swift
                                    vsub.py (merge+vote)             asrsplit.py (sentences)
                                                        └─────────────┬─────────────┘
                                                                      ▼
                                              subs.md / transcript.txt / meta.json
```

## Why two channels

| | OCR | ASR |
|---|---|---|
| Source | subtitles the author typed | the audio itself |
| Strength | exact numbers, names, punctuation as written | works with any speech, adds punctuation, keeps spoken words subtitles omit |
| Weakness | needs literal subtitles on screen | homophones and numbers are guesses |
| Speed | ~20 s per 7 min (432 frames) | ~7 s per 7 min |

The subtitle probe is trying to answer one question: *is there text that changes over time in the lower third?* Static text (watermarks, logos, lower-thirds templates) is excluded by similarity-clustering across the 5 samples — OCR often reads the same watermark as slightly different strings per frame, so matching is fuzzy (≥0.75) rather than exact.

## Subtitle band detection

`autoband.py` reads `vocr --boxes` output (normalized bboxes, Vision coordinates, origin bottom-left):

1. keep blocks with `y < 0.30` (lower 30% of the frame) and ≥3 characters;
2. cluster across frames: a text that appears in ≥`--repeat` (default 60%) of frames is a watermark;
3. drop watermarks, recount `hit_rate`;
4. band = 10th percentile of block tops → 90th percentile of block bottoms, plus 1.5% padding;
5. reject the band if its height is outside 2%–45%.

`crop` is only trusted when `hit_rate ≥ 0.6` — otherwise OCR runs on the full frame. (A low hit-rate band can land on a chart and produce nonsense.)

## Post-processing

**OCR path** (`vsub.py`): per-frame lines → merge consecutive lines whose normalized forms are equal, contain each other, or have `difflib` ratio ≥ 0.82 → for each merged group, pick the most frequent variant (majority vote), tie-broken by length. This survives the "typewriter" animation and OCR jitter.

**ASR path** (`asrsplit.py`): `transcribe.swift` emits one JSON per final result, with `runs[]` carrying per-word `audioTimeRange`. Sentences are cut on terminal punctuation, or on commas once the buffer exceeds `--maxlen`; a hard cut happens only at 4× that length, because word-level timestamps carry no pause information (all gaps are 0) and cutting mid-word reads badly.

## Timing budget (M-series, 432 s video)

| Step | OCR | ASR |
|---|---|---|
| Acquire | — (file is already local) | same |
| Probe | 0.3 s | — |
| Extract | 5.7 s (432 jpegs) | 0.8 s (wav) |
| Recognize | 19.5 s | 6.8 s |
| Merge/split | 0.2 s | 0.1 s |

Vision's first call in a fresh process pays a one-time model load (~28 s); batch mode pays it once for hundreds of frames.

## Speech framework notes

- `SpeechAnalyzer` + `SpeechTranscriber` (macOS 26+). `DictationTranscriber` is the alternative: better punctuation, ~3× slower.
- Confidence and timing come from `attributeOptions: [.audioTimeRange, .transcriptionConfidence]`.
- Locales must be installed; `AssetInventory.assetInstallationRequest(supporting:)` downloads on demand. `make doctor` prints supported vs installed.
- Dropping `.volatileResults` from `reportingOptions` roughly halves latency — intermediate results are expensive and this tool does not need them.
