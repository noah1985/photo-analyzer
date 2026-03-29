import Foundation

// MARK: - Stream JSONL events from CLI --stream

struct StreamStart: Codable {
    let type: String
    let total: Int
    let sourceDirectory: String
    let requestedCount: Int
    let files: [StreamFileRef]

    enum CodingKeys: String, CodingKey {
        case type, total, files
        case sourceDirectory = "source_directory"
        case requestedCount = "requested_count"
    }
}

struct StreamFileRef: Codable {
    let fileName: String
    let filePath: String

    enum CodingKeys: String, CodingKey {
        case fileName = "file_name"
        case filePath = "file_path"
    }
}

struct StreamProgress: Codable {
    let type: String
    let index: Int
    let fileName: String
    let filePath: String

    enum CodingKeys: String, CodingKey {
        case type, index
        case fileName = "file_name"
        case filePath = "file_path"
    }
}

struct StreamResult: Codable {
    let type: String
    let index: Int
    let fileName: String
    let filePath: String
    let summary: String
    let caption: String?
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case type, index, summary, caption, tags
        case fileName = "file_name"
        case filePath = "file_path"
    }
}

struct StreamError: Codable {
    let type: String
    let index: Int
    let fileName: String
    let filePath: String
    let error: String

    enum CodingKeys: String, CodingKey {
        case type, index, error
        case fileName = "file_name"
        case filePath = "file_path"
    }
}

struct StreamDone: Codable {
    let type: String
    let totalSuccess: Int
    let totalFailed: Int

    enum CodingKeys: String, CodingKey {
        case type
        case totalSuccess = "total_success"
        case totalFailed = "total_failed"
    }
}

// MARK: - Batch JSON (non-stream fallback)

struct CLIResponse: Codable {
    let ok: Bool
    let error: String?
    let items: [CLIItem]?
    let failures: [CLIFailure]?

    enum CodingKeys: String, CodingKey {
        case ok, error, items, failures
    }
}

struct CLIItem: Codable {
    let fileName: String
    let filePath: String
    let summary: String
    let caption: String?
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case summary, caption, tags
        case fileName = "file_name"
        case filePath = "file_path"
    }
}

struct CLIFailure: Codable, Identifiable {
    var id: String { filePath }
    let fileName: String
    let filePath: String
    let error: String

    enum CodingKeys: String, CodingKey {
        case error
        case fileName = "file_name"
        case filePath = "file_path"
    }
}

// MARK: - Display model

struct PhotoResult: Identifiable {
    let id = UUID()
    let fileName: String
    let filePath: String
    let tags: [String]
    let summary: String
}
