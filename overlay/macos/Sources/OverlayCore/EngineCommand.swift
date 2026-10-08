import Foundation

/// How the app starts the engine: `uv run --project <repository> leagueasymode run`.
public struct EngineCommand: Equatable, Sendable {
    /// The program to run; `/usr/bin/env`, which finds `uv` on the search path.
    public let executableURL: URL
    /// Its arguments.
    public let arguments: [String]
    /// Its environment: the app's own, with the places uv is usually installed added to `PATH`.
    public let environment: [String: String]

    /// Where uv is usually installed, below the home directory or at a fixed path.
    static let usualUvDirectories = [".local/bin", ".cargo/bin"]
    static let usualSystemDirectories = ["/opt/homebrew/bin", "/usr/local/bin"]
    static let defaultSearchPath = "/usr/bin:/bin:/usr/sbin:/sbin"

    /// Returns the command that runs the engine from a clone of the repository.
    ///
    /// An app opened from Finder does not inherit the shell's `PATH`, so the usual places of uv
    /// are added after whatever `PATH` the app has.
    ///
    /// - Parameters:
    ///   - repositoryRoot: The clone's root, which holds `pyproject.toml`.
    ///   - inheritedEnvironment: The app's own environment.
    ///   - homeDirectory: The user's home directory.
    /// - Returns: The command.
    public static func make(
        repositoryRoot: URL, inheritedEnvironment: [String: String], homeDirectory: URL
    ) -> EngineCommand {
        let inheritedSearchPath = inheritedEnvironment["PATH"] ?? defaultSearchPath
        let inheritedDirectories = inheritedSearchPath.split(separator: ":").map(String.init)
        let usualDirectories =
            usualUvDirectories.map { homeDirectory.appendingPathComponent($0).path }
            + usualSystemDirectories
        var searchDirectories: [String] = []
        for directory in inheritedDirectories + usualDirectories
        where !directory.isEmpty && !searchDirectories.contains(directory) {
            searchDirectories.append(directory)
        }
        var engineEnvironment = inheritedEnvironment
        engineEnvironment["PATH"] = searchDirectories.joined(separator: ":")
        return EngineCommand(
            executableURL: URL(fileURLWithPath: "/usr/bin/env"),
            arguments: ["uv", "run", "--project", repositoryRoot.path, "leagueasymode", "run"],
            environment: engineEnvironment
        )
    }
}
