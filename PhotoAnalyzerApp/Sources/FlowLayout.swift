import SwiftUI

/// A simple horizontal flow / wrap layout for tags.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        guard !rows.isEmpty else { return .zero }
        let height = rows.reduce(CGFloat(0)) { acc, row in
            acc + row.height
        } + CGFloat(rows.count - 1) * spacing
        return CGSize(width: proposal.width ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = computeRows(proposal: proposal, subviews: subviews)
        var y = bounds.minY
        var subviewIndex = 0
        for row in rows {
            var x = bounds.minX
            for _ in 0..<row.count {
                let size = subviews[subviewIndex].sizeThatFits(.unspecified)
                subviews[subviewIndex].place(at: CGPoint(x: x, y: y), proposal: .unspecified)
                x += size.width + spacing
                subviewIndex += 1
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var count: Int
        var height: CGFloat
    }

    private func computeRows(proposal: ProposedViewSize, subviews: Subviews) -> [Row] {
        let maxWidth = proposal.width ?? .infinity
        var rows: [Row] = []
        var currentWidth: CGFloat = 0
        var currentHeight: CGFloat = 0
        var currentCount = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            let needed = currentCount == 0 ? size.width : size.width + spacing
            if currentCount > 0 && currentWidth + needed > maxWidth {
                rows.append(Row(count: currentCount, height: currentHeight))
                currentWidth = size.width
                currentHeight = size.height
                currentCount = 1
            } else {
                currentWidth += needed
                currentHeight = max(currentHeight, size.height)
                currentCount += 1
            }
        }
        if currentCount > 0 {
            rows.append(Row(count: currentCount, height: currentHeight))
        }
        return rows
    }
}
