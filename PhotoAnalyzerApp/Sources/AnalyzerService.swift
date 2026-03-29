import Foundation

enum AnalyzerError: LocalizedError {
    case pythonNotFound
    case directoryInvalid(String)
    case cliError(String)
    case jsonParseError(String)
    case emptyResult

    var errorDescription: String? {
        switch self {
        case .pythonNotFound:
            return "找不到可用的 python3。请确认已安装 Python 3 且 photo_analyzer 可 import。"
        case .directoryInvalid(let path):
            return "目录无效：\(path)"
        case .cliError(let message):
            return "CLI 执行失败：\(message)"
        case .jsonParseError(let detail):
            return "无法解析分析结果：\(detail)"
        case .emptyResult:
            return "分析完成，但没有返回任何结果。"
        }
    }
}

/// Events emitted during streaming analysis.
enum StreamEvent {
    case start(total: Int, files: [StreamFileRef])
    /// 流式分析在逐张 progress 之前预加载 caption pipeline
    case modelLoading
    case modelDownloadProgress(status: String, percent: Double?, etaSeconds: Double?)
    case modelReady(modelInitializationSeconds: Double)
    /// 开始处理某一文件前发出（模型推理耗时期间界面可显示文件名）
    case progress(index: Int, fileName: String, filePath: String)
    case result(PhotoResult)
    case failure(CLIFailure)
    case done(success: Int, failed: Int)
}

final class AnalyzerService {
    static let bundledUIVersion = "1.1.0"
    static let defaultModelKey = "balanced"
    static let availableModels: [CaptionModelOption] = [
        CaptionModelOption(
            id: "fast",
            title: "快速",
            capability: "主体识别基础稳定，适合快速初筛。",
            speed: "CPU 下通常 2-4 秒/张。"
        ),
        CaptionModelOption(
            id: "balanced",
            title: "平衡",
            capability: "主体和场景判断更稳，推荐默认使用。",
            speed: "CPU 下通常 3-8 秒/张。"
        ),
        CaptionModelOption(
            id: "detailed",
            title: "细节",
            capability: "描述更开放，细节词更多，但有时更发散。",
            speed: "CPU 下通常 4-9 秒/张。"
        ),
        CaptionModelOption(
            id: "photo",
            title: "摄影",
            capability: "摄影方向的补充模型，部分题材更具体，但当前默认仍建议优先使用平衡。",
            speed: "CPU 下通常 4-12 秒/张。"
        ),
    ]

    // MARK: - Python discovery

    private static let pythonCandidates: [String] = [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ]

    static func findPython(projectRoot: String? = nil) -> String? {
        let root = projectRoot ?? guessProjectRoot()
        for candidate in pythonCandidates {
            guard FileManager.default.isExecutableFile(atPath: candidate) else { continue }
            if canImportPhotoAnalyzer(python: candidate, projectRoot: root) {
                return candidate
            }
        }
        return pythonCandidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    private static func canImportPhotoAnalyzer(python: String, projectRoot: String?) -> Bool {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: python)
        task.arguments = ["-c", "import photo_analyzer"]
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        if let root = projectRoot {
            var env = ProcessInfo.processInfo.environment
            env["PYTHONPATH"] = root
            task.environment = env
        }
        do {
            try task.run()
            task.waitUntilExit()
            return task.terminationStatus == 0
        } catch {
            return false
        }
    }

    static func fetchCLIVersion() -> String? {
        let root = guessProjectRoot()
        guard let python = findPython(projectRoot: root) else { return nil }

        let task = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        task.executableURL = URL(fileURLWithPath: python)
        task.arguments = ["-m", "photo_analyzer", "--version"]
        task.standardOutput = stdoutPipe
        task.standardError = stderrPipe

        if let root {
            var env = ProcessInfo.processInfo.environment
            if let existing = env["PYTHONPATH"], !existing.isEmpty {
                env["PYTHONPATH"] = root + ":" + existing
            } else {
                env["PYTHONPATH"] = root
            }
            task.environment = env
            task.currentDirectoryURL = URL(fileURLWithPath: root)
        }

        do {
            try task.run()
            task.waitUntilExit()
            guard task.terminationStatus == 0 else { return nil }
            let data = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            return output?.replacingOccurrences(of: "photo-analyzer ", with: "")
        } catch {
            return nil
        }
    }

    // MARK: - Project root discovery

    static func guessProjectRoot() -> String? {
        var seeds: [URL] = []
        if let bundlePath = Bundle.main.bundlePath as String? {
            seeds.append(URL(fileURLWithPath: bundlePath).deletingLastPathComponent())
        }
        seeds.append(URL(fileURLWithPath: FileManager.default.currentDirectoryPath))
        if let execURL = Bundle.main.executableURL {
            seeds.append(execURL.deletingLastPathComponent())
        }
        for seed in seeds {
            var dir = seed
            for _ in 0..<10 {
                let candidate = dir.appendingPathComponent("pyproject.toml")
                if FileManager.default.fileExists(atPath: candidate.path) {
                    return dir.path
                }
                let parent = dir.deletingLastPathComponent()
                if parent.path == dir.path { break }
                dir = parent
            }
        }
        return nil
    }

    // MARK: - Streaming analysis

    /// Run `analyze-dir --stream` and call `onEvent` for each JSONL line.
    /// The closure is called on a background thread; caller is responsible for dispatching to main.
    static func analyzeDirectoryStreaming(
        at directoryPath: String,
        count: Int,
        modelKey: String,
        onEvent: @escaping (StreamEvent) -> Void
    ) async throws {
        let root = guessProjectRoot()
        guard let python = findPython(projectRoot: root) else {
            throw AnalyzerError.pythonNotFound
        }

        let task = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        task.executableURL = URL(fileURLWithPath: python)
        task.arguments = [
            "-m", "photo_analyzer",
            "analyze-dir", directoryPath,
            "--count", String(count),
            "--model", modelKey,
            "--stream",
        ]
        task.standardOutput = stdoutPipe
        task.standardError = stderrPipe

        if let root {
            var env = ProcessInfo.processInfo.environment
            if let existing = env["PYTHONPATH"], !existing.isEmpty {
                env["PYTHONPATH"] = root + ":" + existing
            } else {
                env["PYTHONPATH"] = root
            }
            task.environment = env
            task.currentDirectoryURL = URL(fileURLWithPath: root)
        }

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try task.run()
                } catch {
                    continuation.resume(throwing: AnalyzerError.cliError(error.localizedDescription))
                    return
                }

                let handle = stdoutPipe.fileHandleForReading
                var buffer = Data()
                let newline = UInt8(ascii: "\n")

                while true {
                    let chunk = handle.availableData
                    if chunk.isEmpty { break }
                    buffer.append(chunk)

                    while let nlIndex = buffer.firstIndex(of: newline) {
                        let lineData = buffer[buffer.startIndex..<nlIndex]
                        buffer = buffer[(nlIndex + 1)...]

                        guard !lineData.isEmpty else { continue }
                        Self.parseStreamLine(Data(lineData), onEvent: onEvent)
                    }
                }
                // Remaining data without trailing newline
                if !buffer.isEmpty {
                    Self.parseStreamLine(Data(buffer), onEvent: onEvent)
                }

                task.waitUntilExit()

                if task.terminationStatus != 0 {
                    let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                    let msg = String(data: stderrData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    continuation.resume(throwing: AnalyzerError.cliError(
                        msg.isEmpty ? "退出码 \(task.terminationStatus)" : msg
                    ))
                } else {
                    continuation.resume()
                }
            }
        }
    }

    private static func parseStreamLine(_ data: Data, onEvent: (StreamEvent) -> Void) {
        let decoder = JSONDecoder()

        // Peek at "type" field
        struct TypePeek: Codable { let type: String }
        guard let peek = try? decoder.decode(TypePeek.self, from: data) else { return }

        switch peek.type {
        case "start":
            if let obj = try? decoder.decode(StreamStart.self, from: data) {
                onEvent(.start(total: obj.total, files: obj.files))
            }
        case "model_loading":
            if (try? decoder.decode(StreamModelLoading.self, from: data)) != nil {
                onEvent(.modelLoading)
            }
        case "model_download_progress":
            if let obj = try? decoder.decode(StreamModelDownloadProgress.self, from: data) {
                onEvent(.modelDownloadProgress(status: obj.status, percent: obj.percent, etaSeconds: obj.etaSeconds))
            }
        case "model_ready":
            if let obj = try? decoder.decode(StreamModelReady.self, from: data) {
                onEvent(.modelReady(modelInitializationSeconds: obj.modelInitializationSeconds))
            }
        case "progress":
            if let obj = try? decoder.decode(StreamProgress.self, from: data) {
                onEvent(.progress(index: obj.index, fileName: obj.fileName, filePath: obj.filePath))
            }
        case "result":
            if let obj = try? decoder.decode(StreamResult.self, from: data) {
                let result = PhotoResult(
                    fileName: obj.fileName,
                    filePath: obj.filePath,
                    captionModel: obj.captionModel,
                    captionModelLabel: obj.captionModelLabel,
                    modelInitializationSeconds: obj.modelInitializationSeconds,
                    analysisDurationSeconds: obj.analysisDurationSeconds,
                    tagGroups: obj.tagGroups,
                    tags: obj.tags,
                    summary: obj.summary
                )
                onEvent(.result(result))
            }
        case "error":
            if let obj = try? decoder.decode(StreamError.self, from: data) {
                let failure = CLIFailure(fileName: obj.fileName, filePath: obj.filePath, error: obj.error)
                onEvent(.failure(failure))
            }
        case "done":
            if let obj = try? decoder.decode(StreamDone.self, from: data) {
                onEvent(.done(success: obj.totalSuccess, failed: obj.totalFailed))
            }
        default:
            break
        }
    }
}
