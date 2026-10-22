# video-transcript

**把任意视频变成带时间戳的文字——本机完成、不花钱。**

[English](README.md) · 简体中文

丢一个小红书链接、本地录屏、还是播客音频进来，拿回一份可以引用、可以检索、可以总结的文稿。不上传、不要 API key、不按分钟计费。

- **两条通道自动选。** 有硬字幕走苹果 Vision OCR，没字幕走苹果 SpeechAnalyzer。
- **7 分钟视频 10–30 秒。** 不租 GPU、不排队。
- **为 agent 设计。** stdout 一个 JSON，字段稳定，警告可执行。

```
7 分 12 秒视频  →  OCR 通道  →  242 条字幕 / 2093 字  →  27 秒
                →  ASR 通道  →  60 句 / 2238 字        →  8.6 秒
```

---

## 🤖 给 agent：自己装

把下面这段丢给任何有 shell 的 agent（Claude Code、Codex、Cursor…）：

> 从 `<repo-url>` 安装 `video-transcript`：克隆到 `~/tools/video-transcript`，
> 运行 `./install.sh --json`，逐条处理 `needs_user` 里的问题——需要 sudo 的先问我。
> 直到 `ready` 为 true，然后跑 `./vsum <一个链接或文件>`，报告它的
> `method`、`chars` 和 `warnings`。

或者一条命令了事：

```bash
git clone <repo-url> ~/tools/video-transcript && ~/tools/video-transcript/install.sh --yes --link
```

`install.sh` 幂等、不需要交互，stdout 只输出**一个 JSON 对象**（进度走 stderr），并且把「它自己修好的」和「只有你能做的」分开：

```json
{
  "ready": false,
  "checks": [{"name": "ffmpeg", "status": "missing", "detail": "not installed"}],
  "fixed": [],
  "needs_user": [
    {"issue": "编译识别器需要 Xcode Command Line Tools",
     "command": "xcode-select --install"}
  ],
  "next": "resolve needs_user, then rerun ./install.sh --json"
}
```

| 退出码 | 含义 |
|---|---|
| 0 | 就绪，`./vsum <输入>` 可直接用 |
| 1 | 卡在 `needs_user` |
| 2 | 安装器本身出错 |

给 agent 的提示：`xcode-select --install` 会弹 GUI 窗口，这一项要交给用户；`brew install ffmpeg` 可以自己跑（或直接传 `--yes`）。node 是可选的，只有从网页取流时才需要。

---

## 为什么这么做

把 432 帧喂给视觉模型当然能出结果，但又慢又贵，而那 432 帧里九成是装饰性动画。一个口播讲解视频真正值得读的只有两样：**作者手打的字幕**（已经校对过的文本）和**说的话**。其余都是壁纸。

所以这个工具只做便宜而精确的事：抽帧，只识别字幕那一条，用 macOS 自带的 OCR 引擎读，然后合并重复。没有字幕就退回系统自带的语音引擎。两者都跑在神经引擎上，成本都是零。

## 环境要求

| | |
|---|---|
| 系统 | macOS 26+（需要 SpeechAnalyzer）。只用 OCR 的话老系统也能跑。 |
| 工具链 | Xcode Command Line Tools（`swiftc`） |
| 运行时 | `ffmpeg`、`python3`、`node`（node 仅用于抓网页） |

```bash
./install.sh           # 检查依赖、编译、报告缺什么
./install.sh --json    # 同上，机器可读
./install.sh --link    # 顺便把 ./vsum 软链到 ~/.local/bin
make doctor            # 查看本机支持/已安装哪些语音语言
```

某语言第一次使用会自动下载语音模型（几秒），之后完全离线。

## 用法

```bash
# 网页（借你已登录的 Chrome 解析视频直链）
python3 cli/vsum.py "https://xhslink.cn/o/8p8U68Y44ib"

# 本地文件
python3 cli/vsum.py ~/Movies/lecture.mp4

# 纯音频
python3 cli/vsum.py ~/Downloads/podcast.m4a

# 强制通道
python3 cli/vsum.py video.mp4 --method asr
python3 cli/vsum.py slides.mp4 --method ocr --full
```

产物落在 `out/<标题>/`：

| 文件 | 内容 |
|---|---|
| `subs.md` | 带时间轴，`[MM:SS] 文本` |
| `transcript.txt` | 纯文本 |
| `meta.json` | 通道、判定细节、耗时、警告 |

### 命令行

```
vsum <输入> [--method auto|ocr|asr] [--fps 1] [--out DIR] [--full]
            [--langs zh-Hans,en-US] [--asr-mode transcribe|dictation]
            [--asr-locale zh-CN] [--format json|text] [--keep-work] [--quiet]
```

`--method auto`（默认）不是拍脑袋：它抽 5 帧，只识别画面下部，**把跨帧重复出现的文字（水印、台标）剔掉**，只有当仍有 ≥60% 的帧存在文字时才走 OCR，否则走语音识别。任何显式的 `--method` 都会覆盖它。

### JSON 契约

```json
{
  "ok": true,
  "method": "ocr",
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

`warnings` 才是关键。例如：

- `OCR output density is very low (0.23 chars/s …) — retry with --method asr`：这一趟扫到的是水印不是字幕，换通道重跑。
- `ASR mis-hears numbers and homophones …`：凡是数字，引用前必须核对。

## 实测数据

M 系列 Mac / macOS 27，一条 432 秒 1080p 中文讲解视频：

| | OCR 通道 | ASR 通道 |
|---|---|---|
| 通道探测 | 5 帧，0.3 秒 | — |
| 抽帧 / 抽音轨 | 432 帧，5.7 秒 | 16 kHz 单声道，0.8 秒 |
| 识别 | 19.5 秒（45 ms/帧，8 路并行） | **6.8 秒**（约 60 倍实时） |
| 产出 | 242 段 / 2093 字 | 60 句 / 2238 字 |
| **合计** | **27 秒** | **8.6 秒** |

以作者字幕为参照的准确率：

| 引擎 | 相似度 | 说明 |
|---|---|---|
| Vision OCR | — | 每千字 1–3 处形近字错误 |
| `SpeechTranscriber` | 0.963（CER ≈5.8%） | 快，标点偏少 |
| `DictationTranscriber` | 0.930（CER ≈10.1%） | 标点自然，慢 3 倍 |

ASR 有时"看起来更差"：它把字幕精简掉的口语补了回来（"说白了""你看""群聊红包小程序"）。这些在 CER 里算错，但更忠于原话。

## 给 agent 用

`SKILL.md` 就是给 agent 读的方法论：怎么选通道、怎么读 JSON、怎么处理数字、怎么把文稿整理成"分清作者观点与事实"的总结。把仓库根目录指给 agent，它应该不用额外说明就能跑。

建议把 `SKILL.md` 复制或软链到你的 agent 技能目录。

## 设计取舍

- **只识别字幕带。** 整幅识别会把画面装饰文字混进来，而且准确率更低——同一帧整幅识别把"尽量"读成"风量"，裁到字幕带后读对。
- **1 fps 而不是更高。** 字幕停留 2–4 秒；帧率越高只会把"逐字出现"的中间态也采进来。
- **按相似度合并，不按完全相等。** 逐字动画会让同一句产生多个变体（"开了一家"/"开了—家"），`difflib` ≥0.82 归并，再用多数票定稿。
- **水印只在判定时剔除，不删正文。** 删正文没意义——读总结的模型自然会忽略一直重复的那句；但水印留在**探测**里，会让没字幕的视频看起来像有字幕，直接选错通道。
- **取流走用户自己的 Chrome。** 小红书、公众号这类站点需要真实登录态，静态抓取只会撞登录墙；签名直链几分钟就过期，必须立刻下载。

## 已知限制

- 语音通道的数字和专有名词不可靠（见 `warnings`），引用前核对。
- 图表、K 线、画面上的数字不会被读取；需要时 `--full`，或单独让视觉模型看图。
- 既没字幕又没音轨 → 无内容可提取。
- DRM 视频（Netflix 等）不支持；`blob:` 流拿不到直链。
- 语言需有对应语音模型，`make doctor` 可查。
- 艺术字、竖排字幕、花哨排版的识别率低于干净的讲解字幕。

## 目录结构

```
install.sh          给 agent 跑的安装器（幂等，--json / --yes / --link）
vsum                入口 —— ./vsum <链接|文件>
cli/vsum.py         主流程：取流 → 探测 → 选通道 → 识别 → 报告
cli/vocr.swift      Vision OCR 命令行（批量、并行、裁剪、放大、输出 bbox）
cli/transcribe.swift SpeechAnalyzer 转写（transcribe | dictation）
cli/autoband.py     字幕带探测 + 水印剔除
cli/vsub.py         逐帧 OCR → 字幕段（相似度归并 + 多数票）
cli/asrsplit.py     字级 ASR → 句级时间轴
cli/fetch_video.mjs 通过 Chrome DevTools Protocol 解析视频直链
cli/probe_speech.swift  诊断：本机支持/已安装的语音语言
SKILL.md            agent 方法论
```

## 许可

MIT
