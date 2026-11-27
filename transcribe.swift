import AVFoundation
import Foundation
import Speech

// Invoked by presets.to_srt as: swift transcribe.swift <audio-file> <output.srt>

struct Cue {
    let start: Double
    let end: Double
    let text: String
}

func formatTimestamp(_ seconds: Double) -> String {
    let totalMs = max(0, Int((seconds * 1000).rounded()))
    let ms = totalMs % 1000
    let totalSeconds = totalMs / 1000
    let s = totalSeconds % 60
    let m = (totalSeconds / 60) % 60
    let h = totalSeconds / 3600
    return String(format: "%02d:%02d:%02d,%03d", h, m, s, ms)
}

func buildCues(from text: AttributedString) -> [Cue] {
    var cues: [Cue] = []
    var current = ""
    var start: Double?
    var end: Double?

    func flush() {
        let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
        if let cueStart = start, let cueEnd = end, !trimmed.isEmpty {
            cues.append(Cue(start: cueStart, end: cueEnd, text: trimmed))
        }
        current = ""
        start = nil
        end = nil
    }

    for run in text.runs {
        let piece = String(text[run.range].characters)
        let range = run.audioTimeRange

        if !current.isEmpty, current.count + piece.count > 80 {
            flush()
        }
        if start == nil, let pieceStart = range?.start.seconds {
            start = pieceStart
        }
        current += piece
        if let pieceEnd = range?.end.seconds {
            end = pieceEnd
        }
        if let last = piece.trimmingCharacters(in: .whitespaces).last,
           ".?!".contains(last) {
            flush()
        }
    }
    flush()
    return cues
}

func makeSRT(_ cues: [Cue]) -> String {
    var lines: [String] = []
    for (index, cue) in cues.enumerated() {
        lines.append(String(index + 1))
        lines.append("\(formatTimestamp(cue.start)) --> \(formatTimestamp(cue.end))")
        lines.append(cue.text)
        lines.append("")
    }
    return lines.joined(separator: "\n")
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

do {
    let args = CommandLine.arguments
    guard args.count == 3 else {
        fail("Usage: swift transcribe.swift <audio-file> <output.srt>")
    }

    let locale = Locale(identifier: "en-US")
    let transcriber = SpeechTranscriber(
        locale: locale,
        transcriptionOptions: [],
        reportingOptions: [],
        attributeOptions: [.audioTimeRange]
    )

    if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
        try await request.downloadAndInstall()
    }

    let analyzer = SpeechAnalyzer(modules: [transcriber])
    let file = try AVAudioFile(forReading: URL(fileURLWithPath: args[1]))

    let collector = Task { () -> [Cue] in
        var cues: [Cue] = []
        for try await result in transcriber.results where result.isFinal {
            cues.append(contentsOf: buildCues(from: result.text))
        }
        return cues
    }

    if let last = try await analyzer.analyzeSequence(from: file) {
        try await analyzer.finalizeAndFinish(through: last)
    } else {
        await analyzer.cancelAndFinishNow()
    }

    let cues = try await collector.value
    if cues.isEmpty {
        fail("No speech recognised")
    }

    let out = URL(fileURLWithPath: args[2])
    try makeSRT(cues).write(to: out, atomically: true, encoding: .utf8)
} catch {
    fail(String(describing: error))
}
