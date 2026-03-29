import SwiftUI

@MainActor
final class AppState: ObservableObject {
    @Published var cliVersion: String = "读取中…"

    // Input
    @Published var selectedDirectory: URL?
    @Published var sampleCount: Int = 20

    // Progress
    @Published var isAnalyzing = false
    @Published var totalImages: Int = 0
    @Published var completedImages: Int = 0
    @Published var currentFileName: String = ""

    // Output
    @Published var results: [PhotoResult] = []
    @Published var failures: [CLIFailure] = []
    @Published var statusMessage: String = "选择一个照片文件夹开始分析。"
    @Published var errorMessage: String?

    var directoryName: String {
        selectedDirectory?.lastPathComponent ?? ""
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
        statusMessage = "正在启动分析……"

        Task {
            do {
                try await AnalyzerService.analyzeDirectoryStreaming(
                    at: directory.path,
                    count: count
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
            statusMessage = "共 \(total) 张，准备开始分析……"

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
