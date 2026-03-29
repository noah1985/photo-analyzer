import SwiftUI

/// 固定浅色界面；主内容区纯白，不跟系统深色。
enum LightTheme {
    static let pageBackground = Color.white
    static let panel = Color.white
    static let toolbar = Color.white
    static let border = Color(red: 0.86, green: 0.81, blue: 0.74)
    static let textPrimary = Color(red: 0.125, green: 0.114, blue: 0.094)
    static let textMuted = Color(red: 0.42, green: 0.39, blue: 0.35)
    static let accentGreen = Color(red: 0.141, green: 0.314, blue: 0.275)
    static let accentButton = Color(red: 0.15, green: 0.45, blue: 0.32)
    static let cardSurface = Color.white
    /// 图片占位底，略灰便于区分透明图
    static let imagePlaceholder = Color(red: 0.96, green: 0.96, blue: 0.96)
    static let progressTrack = Color(red: 0.92, green: 0.92, blue: 0.92)
    static let tagBg = Color(red: 0.86, green: 0.91, blue: 0.89)
    static let tagText = Color(red: 0.10, green: 0.24, blue: 0.20)
}
