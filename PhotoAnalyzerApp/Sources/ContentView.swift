import SwiftUI

// MARK: - Root

struct ContentView: View {
    @StateObject private var state = AppState()

    var body: some View {
        ZStack(alignment: .top) {
            LightTheme.pageBackground
                .ignoresSafeArea()

            VStack(spacing: 0) {
                ToolbarArea(state: state)

                if state.isAnalyzing || !state.results.isEmpty {
                    ProgressStrip(state: state)
                }

                if state.isAnalyzing {
                    AnalyzingStatusBanner(state: state)
                }

                if state.results.isEmpty && !state.isAnalyzing {
                    EmptyState(state: state)
                } else {
                    MasonryGallery(state: state)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .frame(width: GalleryFixedLayout.contentWidth)
        .preferredColorScheme(.light)
        .tint(LightTheme.accentGreen)
    }
}

// MARK: - Toolbar

private struct ToolbarArea: View {
    @ObservedObject var state: AppState
    private let uiVersion = AnalyzerService.bundledUIVersion

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 14) {
                Button(action: state.selectDirectory) {
                    HStack(spacing: 6) {
                        Image(systemName: "folder.fill")
                            .foregroundStyle(.white.opacity(0.95))
                        Text(state.selectedDirectory == nil ? "选择目录" : state.directoryName)
                            .lineLimit(1)
                    }
                    .font(.system(size: 13, weight: .medium))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(LightTheme.accentGreen)
                    )
                    .foregroundStyle(.white)
                }
                .buttonStyle(.plain)

                HStack(spacing: 4) {
                    Text("张数")
                        .font(.system(size: 12))
                        .foregroundStyle(LightTheme.textMuted)
                    TextField("", value: $state.sampleCount, format: .number)
                        .frame(width: 44)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 12, design: .monospaced))
                        .colorScheme(.light)
                }

                Picker("模型", selection: $state.selectedModelKey) {
                    ForEach(AnalyzerService.availableModels) { model in
                        Text(model.title).tag(model.id)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 110)

                Button(action: state.startAnalysis) {
                    HStack(spacing: 5) {
                        if state.isAnalyzing {
                            ProgressView()
                                .controlSize(.small)
                                .scaleEffect(0.7)
                        } else {
                            Image(systemName: "play.fill")
                                .font(.system(size: 10))
                        }
                        Text(state.isAnalyzing ? "分析中…" : "开始分析")
                    }
                    .font(.system(size: 13, weight: .semibold))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(state.canStart ? LightTheme.accentButton : Color.gray.opacity(0.22))
                    )
                    .foregroundStyle(state.canStart ? .white : LightTheme.textMuted)
                }
                .buttonStyle(.plain)
                .disabled(!state.canStart)

                Spacer()

                VersionBadgeBar(uiVersion: uiVersion, cliVersion: state.cliVersion)

                if let error = state.errorMessage {
                    ErrorPill(message: error)
                }
            }

            Text("模型说明：\(state.selectedModelOption.capability) \(state.selectedModelOption.speed)")
                .font(.system(size: 12))
                .foregroundStyle(LightTheme.textMuted)

            if !state.batchSummary.isEmpty {
                Text("本次分析：\(state.batchSummary)")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(LightTheme.textPrimary)
            }

            if state.isAnalyzing, let percent = state.downloadProgressPercent {
                VStack(alignment: .leading, spacing: 4) {
                    Text(
                        state.downloadStatusText.isEmpty
                            ? String(format: "模型下载 %.1f%%", percent)
                            : String(format: "%@ %.1f%%", state.downloadStatusText, percent)
                    )
                    .font(.system(size: 11))
                    .foregroundStyle(LightTheme.textMuted)

                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule()
                                .fill(LightTheme.progressTrack)
                            Capsule()
                                .fill(LightTheme.accentGreen)
                                .frame(width: max(0, geo.size.width * (percent / 100.0)))
                        }
                    }
                    .frame(height: 6)

                    if let eta = state.downloadEtaSeconds {
                        Text(String(format: "预计还需 %.0f 秒", eta))
                            .font(.system(size: 11))
                            .foregroundStyle(LightTheme.textMuted)
                    }
                }
                .frame(maxWidth: 280)
            }
        }
        .padding(.horizontal, GalleryFixedLayout.horizontalPadding)
        .padding(.top, 16)
        .padding(.bottom, 12)
        .background(LightTheme.toolbar)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(LightTheme.border.opacity(0.5))
                .frame(height: 1)
        }
    }
}

private struct VersionBadgeBar: View {
    let uiVersion: String
    let cliVersion: String

    var body: some View {
        HStack(spacing: 6) {
            VersionPill(title: "UI", version: uiVersion)
            VersionPill(title: "CLI", version: cliVersion)
        }
    }
}

private struct VersionPill: View {
    let title: String
    let version: String

    var body: some View {
        HStack(spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
            Text(version)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Capsule().fill(LightTheme.tagBg))
        .foregroundStyle(LightTheme.textMuted)
    }
}

private extension AppState {
    var canStart: Bool {
        !isAnalyzing && selectedDirectory != nil
    }
}

// MARK: - Progress strip

private struct ProgressStrip: View {
    @ObservedObject var state: AppState

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                LightTheme.progressTrack

                Rectangle()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.16, green: 0.48, blue: 0.36),
                                Color(red: 0.22, green: 0.62, blue: 0.44),
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: max(0, geo.size.width * state.progress))
                    .animation(.easeInOut(duration: 0.28), value: state.progress)
            }
        }
        .frame(height: 3)
    }
}

// MARK: - Analyzing banner（推理耗时期间显示当前处理哪一张）

private struct AnalyzingStatusBanner: View {
    @ObservedObject var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                Text(state.statusMessage)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(LightTheme.textPrimary)
            }
            if !state.currentFileName.isEmpty {
                Text(state.currentFileName)
                    .font(.system(size: 11, weight: .regular, design: .monospaced))
                    .foregroundStyle(LightTheme.textMuted)
                    .lineLimit(2)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, GalleryFixedLayout.horizontalPadding)
        .padding(.vertical, 10)
        .background(LightTheme.toolbar.opacity(0.92))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(LightTheme.border.opacity(0.35))
                .frame(height: 1)
        }
    }
}

// MARK: - Error pill

private struct ErrorPill: View {
    let message: String
    @State private var showingPopover = false

    var body: some View {
        Button {
            showingPopover = true
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 10))
                Text("出错")
                    .font(.system(size: 11, weight: .medium))
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Capsule().fill(Color.red.opacity(0.1)))
            .foregroundStyle(Color(red: 0.75, green: 0.2, blue: 0.18))
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showingPopover, arrowEdge: .top) {
            VStack(alignment: .leading, spacing: 12) {
                Text("错误详情")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(LightTheme.textPrimary)

                ScrollView {
                    Text(message)
                        .font(.system(size: 12))
                        .foregroundStyle(LightTheme.textPrimary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(minHeight: 90, maxHeight: 220)

                HStack {
                    Spacer()
                    Button("关闭") {
                        showingPopover = false
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(LightTheme.accentGreen)
                }
            }
            .padding(16)
            .frame(width: 360)
        }
    }
}

// MARK: - Empty state

private struct EmptyState: View {
    @ObservedObject var state: AppState

    var body: some View {
        VStack(spacing: 16) {
            Spacer()

            ZStack {
                Circle()
                    .fill(LightTheme.accentGreen.opacity(0.08))
                    .frame(width: 100, height: 100)
                Image(systemName: "photo.stack")
                    .font(.system(size: 38, weight: .light))
                    .foregroundStyle(LightTheme.textMuted.opacity(0.5))
            }

            VStack(spacing: 6) {
                Text("本地照片分析")
                    .font(.system(size: 20, weight: .semibold, design: .rounded))
                    .foregroundStyle(LightTheme.textPrimary)
                Text(
                    state.selectedDirectory == nil
                        ? "选择一个照片文件夹，由本地 Python 分析后展示标签和摘要。"
                        : "已选择「\(state.directoryName)」，点击开始分析。"
                )
                .font(.system(size: 13))
                .foregroundStyle(LightTheme.textMuted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Masonry gallery

private struct MasonryGallery: View {
    @ObservedObject var state: AppState

    private var tileWidth: CGFloat { GalleryFixedLayout.tileWidth }

    var body: some View {
        ScrollView {
            MasonryLayout(
                columns: GalleryFixedLayout.columns,
                spacing: GalleryFixedLayout.columnSpacing,
                fixedTileWidth: tileWidth,
                maxColumnWidth: tileWidth
            ) {
                ForEach(state.results) { result in
                    PhotoCard(result: result, columnWidth: tileWidth)
                }
            }
            .frame(width: GalleryFixedLayout.masonryInnerWidth)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, GalleryFixedLayout.horizontalPadding)
            .padding(.vertical, 12)

            if !state.failures.isEmpty {
                FailuresSection(failures: state.failures)
                    .padding(.horizontal, GalleryFixedLayout.horizontalPadding)
                    .padding(.bottom, 24)
            }
        }
    }
}

// MARK: - Photo card

private struct PhotoCard: View {
    let result: PhotoResult
    /// 与瀑布流列宽一致，图片按原始比例适配此宽度，不拉伸变形。
    var columnWidth: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            thumbnail
            content
        }
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(LightTheme.border.opacity(0.65), lineWidth: 1)
        )
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(LightTheme.cardSurface)
                .shadow(color: .black.opacity(0.06), radius: 8, y: 3)
        )
    }

    @ViewBuilder
    private var thumbnail: some View {
        let url = URL(fileURLWithPath: result.filePath)
        if let nsImage = NSImage(contentsOf: url) {
            let w = max(1, nsImage.size.width)
            let h = max(1, nsImage.size.height)
            let ratio = w / h
            Image(nsImage: nsImage)
                .resizable()
                .aspectRatio(ratio, contentMode: .fit)
                .frame(width: columnWidth)
                .background(LightTheme.imagePlaceholder)
        } else {
            Rectangle()
                .fill(LightTheme.imagePlaceholder)
                .frame(width: columnWidth, height: columnWidth)
                .overlay {
                    Image(systemName: "photo")
                        .font(.system(size: 28, weight: .light))
                        .foregroundStyle(LightTheme.textMuted.opacity(0.4))
                }
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(result.fileName)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(LightTheme.textPrimary)
                .lineLimit(2)

            HStack(spacing: 6) {
                Text(result.captionModelLabel)
                    .font(.system(size: 10, weight: .semibold))
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(LightTheme.tagBg))
                    .foregroundStyle(LightTheme.tagText)

                Text("单张分析 \(result.analysisDurationSeconds, specifier: "%.2f") 秒")
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(LightTheme.textMuted)
            }

            Text(result.summary)
                .font(.system(size: 12))
                .foregroundStyle(LightTheme.textMuted)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)

            GroupedTagSection(title: "题材 / 内容", tags: result.tagGroups.subjectContent)
            GroupedTagSection(title: "场景 / 光线", tags: result.tagGroups.sceneLighting)
            GroupedTagSection(title: "构图 / 景别", tags: result.tagGroups.compositionDistance)
            GroupedTagSection(title: "风格 / 观感", tags: result.tagGroups.styleImpression)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct GroupedTagSection: View {
    let title: String
    let tags: [String]

    var body: some View {
        if !tags.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(LightTheme.textMuted)

                FlowLayout(spacing: 4) {
                    ForEach(tags, id: \.self) { tag in
                        TagChip(label: tag)
                    }
                }
            }
        }
    }
}

// MARK: - Tag chip

private struct TagChip: View {
    let label: String

    var body: some View {
        Text(label)
            .font(.system(size: 10, weight: .medium))
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(Capsule().fill(LightTheme.tagBg))
            .foregroundStyle(LightTheme.tagText)
    }
}

// MARK: - Failures section

private struct FailuresSection: View {
    let failures: [CLIFailure]
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(failures) { fail in
                    HStack(alignment: .top) {
                        Text(fail.fileName)
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .foregroundStyle(LightTheme.textPrimary)
                        Spacer(minLength: 8)
                        Text(fail.error)
                            .font(.system(size: 11))
                            .foregroundStyle(LightTheme.textMuted)
                            .multilineTextAlignment(.trailing)
                    }
                    .padding(.vertical, 2)
                }
            }
        } label: {
            Label("\(failures.count) 张分析失败", systemImage: "exclamationmark.triangle")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Color(red: 0.75, green: 0.45, blue: 0.12))
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.orange.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(LightTheme.border.opacity(0.4), lineWidth: 1)
        )
    }
}
