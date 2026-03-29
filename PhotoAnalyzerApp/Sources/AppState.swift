import SwiftUI

@MainActor
final class AppState: ObservableObject {
    @Published var cliVersion: String = "读取中…"

    // Input
    @Published var selectedDirectory: URL?
    @Published var sampleCount: Int = 20
    @Published var selectedModelKey: String = AnalyzerService.defaultModelKey

    // Progress
    @Published var isAnalyzing = false
    @Published var totalImages: Int = 0
    @Published var completedImages: Int = 0
    @Published var currentFileName: String = ""
    @Published var downloadProgressPercent: Double?
    @Published var downloadEtaSeconds: Double?
    @Published var downloadStatusText: String = ""
    @Published var modelInitializationSeconds: Double = 0
    @Published var totalAnalysisSeconds: Double = 0

    // Output
    @Published var results: [PhotoResult] = []
    @Published var failures: [CLIFailure] = []
    @Published var statusMessage: String = "选择一个照片文件夹开始分析。"
    @Published var errorMessage: String?

    var directoryName: String {
        selectedDirectory?.lastPathComponent ?? ""
    }

    var selectedModelOption: CaptionModelOption {
        AnalyzerService.availableModels.first(where: { $0.id == selectedModelKey })
            ?? AnalyzerService.availableModels[1]
    }

    var batchSummary: String {
        guard !results.isEmpty || !failures.isEmpty else { return "" }
        let total = results.count + failures.count
        return String(
            format: "模型初始化 %.2f 秒，共 %d 张照片，成功 %d 张，失败 %d 张，总耗时 %.2f 秒。",
            modelInitializationSeconds,
            total,
            results.count,
            failures.count,
            totalAnalysisSeconds
        )
    }

    init() {
        cliVersion = AnalyzerService.fetchCLIVersion() ?? "未知"
    }

    var progress: Double {
        guard totalImages > 0 else { return 0 }
        return Double(completedImages) / Double(totalImages)
    }

    func selectDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "请选择包含照片的文件夹"
        panel.prompt = "选择"

        guard panel.runModal() == .OK, let url = panel.url else { return }

        selectedDirectory = url
        results = []
        failures = []
        errorMessage = nil
        statusMessage = "已选择：\(url.lastPathComponent)"
    }

    func startAnalysis() {
        guard let directory = selectedDirectory else {
            errorMessage = "请先选择一个照片目录。"
            return
        }

        let count = max(1, min(100, sampleCount))
        sampleCount = count

        isAnalyzing = true
        errorMessage = nil
        results = []
        failures = []
        totalImages = 0
        completedImages = 0
        currentFileName = ""
        downloadProgressPercent = nil
        downloadEtaSeconds = nil
        downloadStatusText = ""
        modelInitializationSeconds = 0
        totalAnalysisSeconds = 0
        statusMessage = "正在启动分析……"
        let batchStartedAt = Date()

        Task {
            do {
                try await AnalyzerService.analyzeDirectoryStreaming(
                    at: directory.path,
                    count: count,
                    modelKey: selectedModelKey
                ) { [weak self] event in
                    DispatchQueue.main.async {
                        self?.handleEvent(event)
                    }
                }
                // Final status (stream completed without error)
                if results.isEmpty && failures.isEmpty {
                    errorMessage = "分析完成，但没有返回任何结果。"
                    statusMessage = "无结果。"
                }
            } catch {
                errorMessage = error.localizedDescription
                statusMessage = "分析出错。"
            }
            totalAnalysisSeconds = Date().timeIntervalSince(batchStartedAt)
            isAnalyzing = false
            currentFileName = ""
        }
    }

    private func handleEvent(_ event: StreamEvent) {
        switch event {
        case .start(let total, _):
            totalImages = total
            completedImages = 0
            currentFileName = ""
            statusMessage = "共 \(total) 张，准备加载模型……"

        case .modelLoading:
            currentFileName = ""
            statusMessage = "正在加载本地模型……"

        case .modelDownloadProgress(let status, let percent, let etaSeconds):
            downloadStatusText = status
            downloadProgressPercent = percent
            downloadEtaSeconds = etaSeconds
            if let percent {
                if let etaSeconds {
                    statusMessage = String(format: "正在下载模型 %.1f%%，预计还需 %.0f 秒", percent, etaSeconds)
                } else {
                    statusMessage = String(format: "正在下载模型 %.1f%%", percent)
                }
            } else {
                statusMessage = "正在下载模型文件……"
            }

        case .modelReady(let initSec):
            modelInitializationSeconds = initSec
            currentFileName = ""
            downloadProgressPercent = nil
            downloadEtaSeconds = nil
            downloadStatusText = ""
            if totalImages > 0 {
                statusMessage = initSec > 0
                    ? String(format: "模型已就绪（初始化 %.2f 秒），开始逐张分析……", initSec)
                    : "模型已就绪，开始逐张分析……"
            } else {
                statusMessage = "准备分析……"
            }

        case .progress(let index, let fileName, _):
            currentFileName = fileName
            if totalImages > 0 {
                statusMessage = "正在分析第 \(index + 1) / \(totalImages) 张"
            } else {
                statusMessage = "正在分析"
            }

        case .result(let photo):
            results.append(photo)
            completedImages += 1
            currentFileName = photo.fileName
            if modelInitializationSeconds == 0, photo.modelInitializationSeconds > 0 {
                modelInitializationSeconds = photo.modelInitializationSeconds
            }
            statusMessage = "正在分析（\(completedImages)/\(totalImages)）：\(photo.fileName)"

        case .failure(let fail):
            failures.append(fail)
            completedImages += 1
            currentFileName = fail.fileName
            statusMessage = "正在分析（\(completedImages)/\(totalImages)）：\(fail.fileName)（失败）"

        case .done(let success, let failed):
            var msg = "分析完成：\(success) 张成功"
            if failed > 0 { msg += "，\(failed) 张失败" }
            statusMessage = msg
        }
    }
}
