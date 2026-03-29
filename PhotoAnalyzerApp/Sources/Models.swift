import Foundation

struct CaptionModelOption: Identifiable, Hashable {
    let id: String
    let title: String
    let capability: String
    let speed: String
}

struct TagGroups: Codable {
    let subjectContent: [String]
    let sceneLighting: [String]
    let compositionDistance: [String]
    let styleImpression: [String]

    enum CodingKeys: String, CodingKey {
        case subjectContent = "subject_content"
        case sceneLighting = "scene_lighting"
        case compositionDistance = "composition_distance"
        case styleImpression = "style_impression"
    }

    static let empty = TagGroups(
        subjectContent: [],
        sceneLighting: [],
        compositionDistance: [],
        styleImpression: []
    )
}

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

struct StreamModelLoading: Codable {
    let type: String
    let captionModel: String

    enum CodingKeys: String, CodingKey {
        case type
        case captionModel = "caption_model"
    }
}

struct StreamModelReady: Codable {
    let type: String
    let modelInitializationSeconds: Double

    enum CodingKeys: String, CodingKey {
        case type
        case modelInitializationSeconds = "model_initialization_seconds"
    }
}

struct StreamModelDownloadProgress: Codable {
    let type: String
    let phase: String
    let status: String
    let current: Double?
    let total: Double?
    let percent: Double?
    let etaSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case type, phase, status, current, total, percent
        case etaSeconds = "eta_seconds"
    }
}

struct StreamResult: Codable {
    let type: String
    let index: Int
    let fileName: String
    let filePath: String
    let summary: String
    let caption: String?
    let captionModel: String
    let captionModelLabel: String
    let modelInitializationSeconds: Double
    let analysisDurationSeconds: Double
    let tagGroups: TagGroups
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case type, index, summary, caption, tags
        case captionModel = "caption_model"
        case captionModelLabel = "caption_model_label"
        case modelInitializationSeconds = "model_initialization_seconds"
        case analysisDurationSeconds = "analysis_duration_seconds"
        case tagGroups = "tag_groups"
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
    let captionModel: String
    let captionModelLabel: String
    let modelInitializationSeconds: Double
    let analysisDurationSeconds: Double
    let tagGroups: TagGroups
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case summary, caption, tags
        case captionModel = "caption_model"
        case captionModelLabel = "caption_model_label"
        case modelInitializationSeconds = "model_initialization_seconds"
        case analysisDurationSeconds = "analysis_duration_seconds"
        case tagGroups = "tag_groups"
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
    let captionModel: String
    let captionModelLabel: String
    let modelInitializationSeconds: Double
    let analysisDurationSeconds: Double
    let tagGroups: TagGroups
    let tags: [String]
    let summary: String
}
