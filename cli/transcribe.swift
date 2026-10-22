import Foundation
import Speech
import AVFoundation

// transcribe — macOS 本地语音转写（SpeechAnalyzer / SpeechTranscriber / DictationTranscriber）
// 用法: transcribe <audio> [locale] [--mode dictation|transcribe]
// 输出: 每行 JSON {"start":秒,"end":秒,"text":"...","runs":[{s,e,t}]}
// 说明: dictation 模式带标点、断句更自然；transcribe 模式为长音频转写

var argv = Array(CommandLine.arguments.dropFirst())
var mode = "dictation"
var positional: [String] = []
var i = 0
while i < argv.count {
    if argv[i] == "--mode", i + 1 < argv.count { mode = argv[i + 1]; i += 2; continue }
    positional.append(argv[i]); i += 1
}
guard let path = positional.first else {
    FileHandle.standardError.write("usage: transcribe <audio> [locale] [--mode dictation|transcribe]\n".data(using: .utf8)!)
    exit(2)
}
let localeId = positional.count > 1 ? positional[1] : "zh-CN"
let locale = Locale(identifier: localeId)
let sem = DispatchSemaphore(value: 0)
var exitCode: Int32 = 0

func emit(start: Double, end: Double, text: String, runs: [[String: Any]]) {
    let obj: [String: Any] = ["start": start, "end": end, "text": text, "runs": runs]
    if let d = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: d, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

func extractRuns(_ attr: AttributedString) -> [[String: Any]] {
    var out: [[String: Any]] = []
    for run in attr.runs {
        guard let r = run.audioTimeRange else { continue }
        out.append(["s": r.start.seconds, "e": r.end.seconds,
                    "t": String(attr[run.range].characters)])
    }
    return out
}

Task {
    do {
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        let dur = Double(file.length) / file.fileFormat.sampleRate
        FileHandle.standardError.write("[asr] 音频 \(String(format: "%.1f", dur))s，模式 \(mode)\n".data(using: .utf8)!)

        if mode == "transcribe" {
            let t = SpeechTranscriber(locale: locale, transcriptionOptions: [],
                                      reportingOptions: [],
                                      attributeOptions: [.audioTimeRange, .transcriptionConfidence])
            if let req = try await AssetInventory.assetInstallationRequest(supporting: [t]) {
                FileHandle.standardError.write("[asr] 安装模型…\n".data(using: .utf8)!)
                try await req.downloadAndInstall()
            }
            let analyzer = SpeechAnalyzer(modules: [t])
            let drain = Task {
                for try await r in t.results where r.isFinal {
                    emit(start: r.range.start.seconds, end: r.range.end.seconds,
                         text: String(r.text.characters), runs: extractRuns(r.text))
                }
            }
            _ = try await analyzer.analyzeSequence(from: file)
            try await analyzer.finalizeAndFinishThroughEndOfInput()
            _ = try await drain.value
            try await analyzer.setModules([])
        } else {
            let t = DictationTranscriber(locale: locale, contentHints: [],
                                         transcriptionOptions: [.punctuation],
                                         reportingOptions: [],
                                         attributeOptions: [.audioTimeRange, .transcriptionConfidence])
            if let req = try await AssetInventory.assetInstallationRequest(supporting: [t]) {
                FileHandle.standardError.write("[asr] 安装模型…\n".data(using: .utf8)!)
                try await req.downloadAndInstall()
            }
            let analyzer = SpeechAnalyzer(modules: [t])
            let drain = Task {
                for try await r in t.results where r.isFinal {
                    emit(start: r.range.start.seconds, end: r.range.end.seconds,
                         text: String(r.text.characters), runs: extractRuns(r.text))
                }
            }
            _ = try await analyzer.analyzeSequence(from: file)
            try await analyzer.finalizeAndFinishThroughEndOfInput()
            _ = try await drain.value
            try await analyzer.setModules([])
        }
        FileHandle.standardError.write("[asr] 完成\n".data(using: .utf8)!)
        sem.signal()
    } catch {
        FileHandle.standardError.write("[asr] 错误: \(error)\n".data(using: .utf8)!)
        exitCode = 1
        sem.signal()
    }
}
sem.wait()
exit(exitCode)
