import Foundation

/// The engine an app bundle carries: a copy of uv, the engine's wheel, the versions uv.lock pins
/// and the Python version the project names.
///
/// `overlay/macos/scripts/build_app.sh` puts them there, uv where a bundle keeps its helper tools:
///
///     Contents/Helpers/uv
///     Contents/Resources/engine/leagueasymode-<version>-py3-none-any.whl
///     Contents/Resources/engine/constraints.txt
///     Contents/Resources/engine/python-version
public struct BundledEngine: Equatable, Sendable {
    /// The bundled uv.
    public let uvURL: URL
    /// The engine's wheel.
    public let wheelURL: URL
    /// The versions uv.lock pins, one requirement a line, which hold the engine's dependencies.
    public let constraintsURL: URL
    /// The Python version the project names (`.python-version`), or nil when the bundle has none.
    public let pythonVersion: String?

    static let uvPath = "Helpers/uv"
    static let engineDirectoryPath = "Resources/engine"
    static let constraintsFileName = "constraints.txt"
    static let pythonVersionFileName = "python-version"
    static let wheelExtension = "whl"

    /// Returns the engine in a bundle, or nil when it does not hold one: no executable uv, no wheel
    /// or no constraints. With more than one wheel, the last by name is used.
    ///
    /// - Parameters:
    ///   - contentsURL: The bundle's `Contents` directory.
    ///   - fileManager: Where to look.
    /// - Returns: The bundled engine, or nil.
    public static func locate(contentsURL: URL, fileManager: FileManager = .default) -> BundledEngine? {
        let uvURL = contentsURL.appendingPathComponent(uvPath)
        let engineDirectory = contentsURL.appendingPathComponent(engineDirectoryPath, isDirectory: true)
        let constraintsURL = engineDirectory.appendingPathComponent(constraintsFileName)
        guard
            fileManager.isExecutableFile(atPath: uvURL.path),
            fileManager.fileExists(atPath: constraintsURL.path),
            let fileNames = try? fileManager.contentsOfDirectory(atPath: engineDirectory.path),
            let wheelName = fileNames.filter({ $0.hasSuffix(".\(wheelExtension)") }).sorted().last
        else {
            return nil
        }
        let pythonVersionURL = engineDirectory.appendingPathComponent(pythonVersionFileName)
        let pythonVersion = (try? String(contentsOf: pythonVersionURL, encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return BundledEngine(
            uvURL: uvURL,
            wheelURL: engineDirectory.appendingPathComponent(wheelName),
            constraintsURL: constraintsURL,
            pythonVersion: pythonVersion?.isEmpty == false ? pythonVersion : nil
        )
    }
}
