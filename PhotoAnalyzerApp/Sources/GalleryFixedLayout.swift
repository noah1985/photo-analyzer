import CoreGraphics

/// 固定 5 列 × 300pt 宽格子；窗口内容宽度由此推导，横向不可拉，仅可拉高。
enum GalleryFixedLayout {
    static let columns: Int = 5
    static let tileWidth: CGFloat = 300
    static let columnSpacing: CGFloat = 14
    static let horizontalPadding: CGFloat = 20

    /// 五列图片区宽度（不含左右 padding）
    static var masonryInnerWidth: CGFloat {
        CGFloat(columns) * tileWidth + CGFloat(columns - 1) * columnSpacing
    }

    /// 与 ScrollView 内左右 padding 一致时的总内容宽（工具栏、瀑布流同宽）
    static var contentWidth: CGFloat {
        masonryInnerWidth + horizontalPadding * 2
    }
}
