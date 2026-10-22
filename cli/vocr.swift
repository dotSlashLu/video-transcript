#!/usr/bin/env swift
// vocr — macOS 原生 Vision OCR 命令行工具（批量/并行）
// 用法: vocr [--bottom 0.16] [--crop x,y,w,h] [--langs zh-Hans,en-US] [--fast] [--scale 2] [--jobs 8] [--boxes] file...
//   --bottom N       只识别底部 N 比例高度（字幕带）
//   --crop x,y,w,h   相对坐标裁剪（左上角原点，x 向右，y 向下）
//   --scale N        先放大 N 倍再识别
//   --boxes          输出每行文本的归一化 bbox（Vision 坐标：原点左下角）
// 输出: 每张图一行 JSON {"file":...,"lines":[...]}  或带 --boxes 时 {"file":...,"boxes":[{text,x,y,w,h}]}
import Foundation
import Vision
import AppKit
import CoreGraphics

var files: [String] = []
var bottom = 0.0
var cropRect: CGRect? = nil
var langs = ["zh-Hans", "en-US"]
var fast = false
var scale = 1.0
var jobs = 6
var emitBoxes = false

var argv = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < argv.count {
    switch argv[i] {
    case "--bottom": i += 1; bottom = Double(argv[i]) ?? 0
    case "--crop":
        i += 1
        let p = argv[i].split(separator: ",").compactMap { Double($0) }
        if p.count == 4 { cropRect = CGRect(x: p[0], y: p[1], width: p[2], height: p[3]) }
    case "--langs": i += 1; langs = argv[i].split(separator: ",").map(String.init)
    case "--scale": i += 1; scale = Double(argv[i]) ?? 1
    case "--jobs": i += 1; jobs = Int(argv[i]) ?? 6
    case "--fast": fast = true
    case "--boxes": emitBoxes = true
    default: files.append(argv[i])
    }
    i += 1
}

func prepare(_ path: String) -> CGImage? {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
    var target = cg
    if bottom > 0 {
        let h = Int((Double(cg.height) * bottom).rounded())
        if let c = cg.cropping(to: CGRect(x: 0, y: cg.height - h, width: cg.width, height: h)) { target = c }
    } else if let r = cropRect {
        // CGImage 坐标系原点在左上角
        let rect = CGRect(x: r.origin.x * Double(cg.width), y: r.origin.y * Double(cg.height),
                          width: r.width * Double(cg.width), height: r.height * Double(cg.height))
        if let c = cg.cropping(to: rect) { target = c }
    }
    if scale != 1.0 {
        let w = Int(Double(target.width) * scale), h = Int(Double(target.height) * scale)
        if let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                               space: CGColorSpaceCreateDeviceRGB(),
                               bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) {
            ctx.interpolationQuality = .high
            ctx.draw(target, in: CGRect(x: 0, y: 0, width: w, height: h))
            if let s = ctx.makeImage() { target = s }
        }
    }
    return target
}

func recognize(_ path: String) -> [[String: Any]] {
    guard let cg = prepare(path) else { return [] }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = fast ? .fast : .accurate
    req.recognitionLanguages = langs
    req.usesLanguageCorrection = true
    if #available(macOS 13.0, *) { req.revision = VNRecognizeTextRequestRevision3 }
    do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req]) } catch { return [] }
    let obs = (req.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }
    return obs.compactMap { o in
        guard let t = o.topCandidates(1).first?.string else { return nil }
        let b = o.boundingBox
        return ["text": t, "x": b.origin.x, "y": b.origin.y, "w": b.width, "h": b.height]
    }
}

let t0 = Date()
var out = [[String: Any]]()
let lock = NSLock()
out.reserveCapacity(files.count)
let chunk = max(1, Int(ceil(Double(files.count) / Double(max(1, jobs)))))
let chunks = stride(from: 0, to: files.count, by: chunk).map { Array(files[$0..<min($0 + chunk, files.count)]) }

DispatchQueue.concurrentPerform(iterations: chunks.count) { ci in
    var local = [[String: Any]]()
    for f in chunks[ci] {
        let rows = recognize(f)
        if emitBoxes {
            local.append(["file": f, "boxes": rows])
        } else {
            local.append(["file": f, "lines": rows.map { $0["text"] as? String ?? "" }])
        }
    }
    lock.lock(); out.append(contentsOf: local); lock.unlock()
}

let order = Dictionary(uniqueKeysWithValues: files.enumerated().map { ($1, $0) })
for d in out.sorted(by: { (order[$0["file"] as? String ?? ""] ?? 0) < (order[$1["file"] as? String ?? ""] ?? 0) }) {
    if let data = try? JSONSerialization.data(withJSONObject: d, options: [.withoutEscapingSlashes]),
       let s = String(data: data, encoding: .utf8) { print(s) }
}
FileHandle.standardError.write("[vocr] \(files.count) 张 / \(String(format: "%.2f", Date().timeIntervalSince(t0)))s\n".data(using: .utf8)!)
