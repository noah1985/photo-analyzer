// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PhotoAnalyzerApp",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "PhotoAnalyzerApp",
            path: "Sources"
        ),
    ]
)
