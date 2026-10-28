import Foundation

/// Where the engine's output is kept. The app opened from Finder has nowhere to show it, so before
/// this an engine that stopped ("Engine: stopped (exit 1)") said nothing about why. Each start of
/// the engine writes a new `engine.log`; the last three runs' are kept.
public enum EngineLog {
    /// How many runs' logs are kept, the current one included.
    public static let keptRunCount = 3

    /// Returns the folder macOS keeps an app's logs in: `~/Library/Logs/LeagueasyMode`.
    ///
    /// - Parameter homeDirectory: The home folder.
    /// - Returns: The folder.
    public static func directory(homeDirectory: URL) -> URL {
        homeDirectory
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("Logs", isDirectory: true)
            .appendingPathComponent("LeagueasyMode", isDirectory: true)
    }

    /// Moves the older logs along (`engine.log` to `engine.1.log`, and so on, the oldest dropped)
    /// and returns where this run's log goes, the file created empty.
    ///
    /// - Parameter directory: The logs' folder, created when missing.
    /// - Returns: This run's log.
    /// - Throws: An error of the file system.
    public static func startNewLog(in directory: URL) throws -> URL {
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        let oldest = logURL(in: directory, run: keptRunCount - 1)
        if fileManager.fileExists(atPath: oldest.path) {
            try fileManager.removeItem(at: oldest)
        }
        for run in stride(from: keptRunCount - 2, through: 0, by: -1) {
            let older = logURL(in: directory, run: run)
            if fileManager.fileExists(atPath: older.path) {
                try fileManager.moveItem(at: older, to: logURL(in: directory, run: run + 1))
            }
        }
        let current = logURL(in: directory, run: 0)
        fileManager.createFile(atPath: current.path, contents: nil)
        return current
    }

    /// The log of a run: 0 the current one (`engine.log`), 1 the one before (`engine.1.log`).
    static func logURL(in directory: URL, run: Int) -> URL {
        directory.appendingPathComponent(run == 0 ? "engine.log" : "engine.\(run).log")
    }
}
