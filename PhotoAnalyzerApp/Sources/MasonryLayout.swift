import SwiftUI

/// 瀑布流：每列固定宽度 `tileWidth`，高度由子视图自己决定；下一项进当前最短的列。
struct MasonryLayout: Layout {
    var columns: Int
    var spacing: CGFloat = 14
    /// 若指定，则列宽用该值（与 PhotoCard 一致）；否则按总宽均分并受 maxColumnWidth 限制。
    var fixedTileWidth: CGFloat?

    var maxColumnWidth: CGFloat = 300

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let totalW = proposal.width ?? 0
        guard columns > 0, totalW > 0 else { return proposal.replacingUnspecifiedDimensions() }

        let colW = resolvedColumnWidth(totalWidth: totalW)
        var colHeights = [CGFloat](repeating: 0, count: columns)

        for subview in subviews {
            let h = subview.sizeThatFits(ProposedViewSize(width: colW, height: nil)).height
            let idx = colHeights.indices.min(by: { colHeights[$0] < colHeights[$1] }) ?? 0
            let gap = colHeights[idx] > 0 ? spacing : 0
            colHeights[idx] += gap + h
        }

        let maxH = colHeights.max() ?? 0
        return CGSize(width: totalW, height: maxH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let colW = resolvedColumnWidth(totalWidth: bounds.width)
        var colHeights = [CGFloat](repeating: 0, count: columns)
        let colXs: [CGFloat] = (0..<columns).map { i in
            bounds.minX + CGFloat(i) * (colW + spacing)
        }

        for subview in subviews {
            let h = subview.sizeThatFits(ProposedViewSize(width: colW, height: nil)).height
            let idx = colHeights.indices.min(by: { colHeights[$0] < colHeights[$1] }) ?? 0
            let gap = colHeights[idx] > 0 ? spacing : 0
            let y = bounds.minY + colHeights[idx] + gap
            subview.place(
                at: CGPoint(x: colXs[idx], y: y),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: colW, height: h)
            )
            colHeights[idx] += gap + h
        }
    }

    private func resolvedColumnWidth(totalWidth: CGFloat) -> CGFloat {
        if let fixed = fixedTileWidth {
            return min(maxColumnWidth, max(80, fixed))
        }
        guard columns > 0 else { return totalWidth }
        let gaps = spacing * CGFloat(max(0, columns - 1))
        var raw = (totalWidth - gaps) / CGFloat(columns)
        raw = min(maxColumnWidth, raw)
        return max(80, raw)
    }
}
