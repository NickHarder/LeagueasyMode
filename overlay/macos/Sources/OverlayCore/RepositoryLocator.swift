import Foundation

/// Finds the clone of the repository the app was built from, which holds the engine.
public enum RepositoryLocator {
    /// An environment variable that names the repository's root, overriding the search.
    public static let overrideVariable = "LEAGUEASYMODE_REPOSITORY"

    /// Returns the repository's root: the variable's value when it is set, otherwise the nearest
    /// directory above `sourceFileURL` that holds both `pyproject.toml` and `overlay/macos`.
    ///
    /// - Parameters:
    ///   - sourceFileURL: A file inside the repository, such as this app's own source file
    ///     (`#filePath`), which a build made from a clone keeps.
    ///   - environment: The app's environment.
    ///   - fileManager: Where to look for the marker files.
    /// - Returns: The root, or nil when neither the variable nor the search finds it.
    public static func repositoryRoot(
        sourceFileURL: URL, environment: [String: String], fileManager: FileManager = .default
    ) -> URL? {
        if let overridePath = environment[overrideVariable], !overridePath.isEmpty {
            return URL(fileURLWithPath: overridePath, isDirectory: true)
        }
        var candidateDirectory = sourceFileURL.deletingLastPathComponent()
        while candidateDirectory.path != "/" && !candidateDirectory.path.isEmpty {
            let projectFilePath = candidateDirectory.appendingPathComponent("pyproject.toml").path
            let overlayDirectoryPath = candidateDirectory.appendingPathComponent("overlay/macos").path
            if fileManager.fileExists(atPath: projectFilePath)
                && fileManager.fileExists(atPath: overlayDirectoryPath)
            {
                return candidateDirectory
            }
            candidateDirectory = candidateDirectory.deletingLastPathComponent()
        }
        return nil
    }
}
