import Foundation

/// How the app starts the engine: from the engine the app bundle carries
/// (`uv tool run --from <wheel> leagueasymode run`), or from a clone of the repository
/// (`uv run --project <repository> leagueasymode run`).
public struct EngineCommand: Equatable, Sendable {
    /// The program to run: the bundled uv, or `/usr/bin/env`, which finds `uv` on the search path.
    public let executableURL: URL
    /// Its arguments.
    public let arguments: [String]
    /// Its environment: the app's own; for a clone, with the places uv is usually installed added to
    /// `PATH`.
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

    /// Returns the command that runs the engine the app bundle carries.
    ///
    /// uv makes an environment from the wheel, holding the dependencies to the versions uv.lock
    /// pins, and keeps it in its cache: the first start downloads them, and Python when no
    /// suitable one is installed; later starts reuse them.
    ///
    /// - Parameters:
    ///   - bundledEngine: The bundle's uv, wheel, constraints and Python version.
    ///   - inheritedEnvironment: The app's own environment, passed on unchanged.
    /// - Returns: The command.
    public static func make(
        bundledEngine: BundledEngine, inheritedEnvironment: [String: String]
    ) -> EngineCommand {
        let pythonArguments = bundledEngine.pythonVersion.map { ["--python", $0] } ?? []
        return EngineCommand(
            executableURL: bundledEngine.uvURL,
            arguments: ["tool", "run", "--from", bundledEngine.wheelURL.path]
                + ["--constraints", bundledEngine.constraintsURL.path]
                + pythonArguments
                + ["leagueasymode", "run"],
            environment: inheritedEnvironment
        )
    }

    /// Returns the command for the engine the app should run: the one its bundle carries, or else
    /// the one in the clone it was built from. Setting the repository variable
    /// (`RepositoryLocator.overrideVariable`) prefers the clone, to try a change to the engine in the
    /// packaged app.
    ///
    /// - Parameters:
    ///   - environment: The app's environment.
    ///   - contentsURL: The app bundle's `Contents` directory, which a build that is no bundle lacks.
    ///   - sourceFileURL: A file inside the clone, such as the app's own source file (`#filePath`).
    ///   - homeDirectory: The user's home directory.
    ///   - fileManager: Where to look.
    /// - Returns: The command, or nil when the app has neither a bundled engine nor a clone.
    public static func choose(
        environment: [String: String],
        contentsURL: URL,
        sourceFileURL: URL,
        homeDirectory: URL,
        fileManager: FileManager = .default
    ) -> EngineCommand? {
        let prefersClone = !(environment[RepositoryLocator.overrideVariable] ?? "").isEmpty
        if !prefersClone,
            let bundledEngine = BundledEngine.locate(contentsURL: contentsURL, fileManager: fileManager)
        {
            return make(bundledEngine: bundledEngine, inheritedEnvironment: environment)
        }
        guard
            let repositoryRoot = RepositoryLocator.repositoryRoot(
                sourceFileURL: sourceFileURL, environment: environment, fileManager: fileManager
            )
        else {
            return nil
        }
        return make(
            repositoryRoot: repositoryRoot,
            inheritedEnvironment: environment,
            homeDirectory: homeDirectory
        )
    }
}
