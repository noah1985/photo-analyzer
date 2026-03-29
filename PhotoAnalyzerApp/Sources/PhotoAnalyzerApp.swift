import AppKit
import SwiftUI

@main
struct PhotoAnalyzerApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minHeight: 480)
                .background(LockWindowContentWidth())
                .preferredColorScheme(.light)
                // 勿在 App.init 里改 NSApp.appearance，此时 NSApplication 未就绪会崩溃。
                .onAppear {
                    DispatchQueue.main.async {
                        NSApplication.shared.appearance = NSAppearance(named: .aqua)
                    }
                }
        }
        .defaultSize(width: GalleryFixedLayout.contentWidth, height: 780)
    }
}

/// 锁定内容区宽度为 5×300 布局对应宽度，仅允许纵向改变窗口高度。
private struct LockWindowContentWidth: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        WindowWidthLockView()
    }

    func updateNSView(_ view: NSView, context: Context) {
        (view as? WindowWidthLockView)?.applyWidthLock()
    }
}

private final class WindowWidthLockView: NSView {
    private var didSnapFrameWidth = false

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        applyWidthLock()
        if window != nil, !didSnapFrameWidth {
            didSnapFrameWidth = true
            snapWindowFrameWidthIfNeeded()
        }
    }

    override func layout() {
        super.layout()
        applyWidthLock()
    }

    fileprivate func applyWidthLock() {
        guard let win = window else { return }
        let contentW = GalleryFixedLayout.contentWidth
        let probeH = max(win.contentView?.bounds.height ?? 400, 320)
        let frameForFixedContent = win.frameRect(
            forContentRect: NSRect(x: 0, y: 0, width: contentW, height: probeH)
        )
        let fixedFrameWidth = frameForFixedContent.width

        var minFrame = win.minSize
        var maxFrame = win.maxSize
        minFrame.width = fixedFrameWidth
        maxFrame.width = fixedFrameWidth
        if minFrame.height < 320 { minFrame.height = 320 }
        if maxFrame.height < minFrame.height { maxFrame.height = 10_000 }
        win.minSize = minFrame
        win.maxSize = maxFrame

        var cmin = win.contentMinSize
        var cmax = win.contentMaxSize
        cmin.width = contentW
        cmax.width = contentW
        if cmin.height < 320 { cmin.height = 320 }
        if cmax.height < cmin.height { cmax.height = 10_000 }
        win.contentMinSize = cmin
        win.contentMaxSize = cmax
    }

    /// 把窗口框架宽度收束到与固定内容宽一致（仅首次），避免默认窗口宽与内容不一致时仍可横向拖动改变宽度。
    private func snapWindowFrameWidthIfNeeded() {
        guard let win = window else { return }
        let contentW = GalleryFixedLayout.contentWidth
        let cr = win.contentRect(forFrameRect: win.frame)
        let contentH = max(cr.height, 320)
        let idealFrame = win.frameRect(
            forContentRect: NSRect(x: 0, y: 0, width: contentW, height: contentH)
        )
        var f = win.frame
        guard abs(f.size.width - idealFrame.width) > 1 else { return }
        let dx = (f.size.width - idealFrame.width) / 2
        f.size.width = idealFrame.width
        f.origin.x += dx
        win.setFrame(f, display: true, animate: false)
    }
}
