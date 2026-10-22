import Foundation
import Speech

// 探测 macOS 原生语音识别能力
print("=== 系统 ===")
print(ProcessInfo.processInfo.operatingSystemVersionString)

// 1) 新版 SpeechTranscriber (macOS 26+)
if #available(macOS 26.0, *) {
    let supported = await SpeechTranscriber.supportedLocales
    let installed = await SpeechTranscriber.installedLocales
    print("\n=== SpeechTranscriber.supportedLocales (\(supported.count)) ===")
    print(supported.map { $0.identifier(.bcp47) }.sorted().joined(separator: " "))
    print("\n=== SpeechTranscriber.installedLocales (\(installed.count)) ===")
    print(installed.map { $0.identifier(.bcp47) }.sorted().joined(separator: " "))
    print("\n中文支持: supported=\(supported.contains { $0.language.languageCode?.identifier == "zh" }) installed=\(installed.contains { $0.language.languageCode?.identifier == "zh" })")
} else {
    print("SpeechTranscriber 不可用（需 macOS 26+）")
}

// 2) 老版 SFSpeechRecognizer
print("\n=== SFSpeechRecognizer ===")
for id in ["zh-CN", "zh-Hans-CN", "en-US"] {
    if let r = SFSpeechRecognizer(locale: Locale(identifier: id)) {
        print("\(id): available=\(r.isAvailable) onDevice=\(r.supportsOnDeviceRecognition)")
    } else {
        print("\(id): nil")
    }
}
print("授权状态: \(SFSpeechRecognizer.authorizationStatus().rawValue) (0=未决,1=受限,2=拒绝,3=已授权)")
