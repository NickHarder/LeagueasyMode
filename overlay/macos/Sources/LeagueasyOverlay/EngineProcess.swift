import Foundation
import OverlayCore

/// Runs the engine (`leagueasymode run`) as a child process and reports what it announces.
///
/// The engine's standard output is read for the line with the overlay's address. Its log, its
/// standard error and output both, goes to this run's `engine.log` (`EngineLog`), or to the app's
/// standard error, as under `swift run`, when there is no log file.
final class EngineProcess {
    private let process = Process()
    private let outputPipe = Pipe()

    /// Prepares the process; nothing runs until `start`.
    ///
    /// - Parameters:
    ///   - command: How to run the engine.
    ///   - onOverlayURL: Called on the main actor with the overlay's address, once the engine is up.
    ///   - onExit: Called on the main actor with the engine's exit status, when it stops.
    init(
        command: EngineCommand,
        logURL: URL?,
        extraEnvironment: [String: String],
        onOverlayURL: @escaping @MainActor @Sendable (URL) -> Void,
        onExit: @escaping @MainActor @Sendable (Int32) -> Void
    ) {
        process.executableURL = command.executableURL
        process.arguments = command.arguments
        process.environment = command.environment.merging(extraEnvironment) { _, added in added }
        process.standardOutput = outputPipe
        let logWriter = LogWriter(logURL: logURL)
        process.standardError = logWriter.fileHandle ?? FileHandle.standardError
        let outputLines = OutputLines()
        outputPipe.fileHandleForReading.readabilityHandler = { outputHandle in
            let newBytes = outputHandle.availableData
            guard !newBytes.isEmpty else {
                return
            }
            logWriter.write(newBytes)
            for outputLine in outputLines.append(newBytes) {
                if let overlayURL = EngineAnnouncement.overlayURL(fromLine: outputLine) {
                    Task { @MainActor in onOverlayURL(overlayURL) }
                }
            }
        }
        process.terminationHandler = { finishedProcess in
            let exitStatus = finishedProcess.terminationStatus
            Task { @MainActor in onExit(exitStatus) }
        }
    }

    /// Starts the engine.
    ///
    /// - Throws: The error `Process.run` gives when the program cannot be started.
    func start() throws {
        try process.run()
    }

    /// Asks the engine to stop. It closes the game it is recording before it exits, so this does
    /// not wait for it.
    func stop() {
        if process.isRunning {
            process.terminate()
        }
    }
}

/// This run's engine log, written from the output pipe's queue; the lock keeps writes whole.
private final class LogWriter: @unchecked Sendable {
    private let lock = NSLock()
    let fileHandle: FileHandle?

    /// Opens the log for writing, or nothing when there is none or it cannot be opened.
    ///
    /// - Parameter logURL: The log, created empty; nil for none.
    init(logURL: URL?) {
        fileHandle = logURL.flatMap { try? FileHandle(forWritingTo: $0) }
    }

    /// Appends bytes of the engine's output to the log.
    ///
    /// - Parameter bytes: The bytes.
    func write(_ bytes: Data) {
        lock.lock()
        defer { lock.unlock() }
        fileHandle?.write(bytes)
    }
}

/// The engine's output, cut into whole lines as it arrives. The pipe's handler runs on a queue of
/// its own; the lock keeps the buffer to one caller at a time all the same.
private final class OutputLines: @unchecked Sendable {
    private let lock = NSLock()
    private var lineBuffer = LineBuffer()

    /// Takes the next bytes and returns the lines they complete.
    ///
    /// - Parameter newBytes: The bytes.
    /// - Returns: The whole lines, without their line breaks.
    func append(_ newBytes: Data) -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return lineBuffer.append(newBytes)
    }
}
