import Foundation
import OverlayCore

/// Runs the engine (`leagueasymode run`) as a child process and reports what it announces.
///
/// The engine's standard output is read for the line with the overlay's address; its standard
/// error goes to the app's, so `swift run` shows the engine's log.
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
        onOverlayURL: @escaping @MainActor @Sendable (URL) -> Void,
        onExit: @escaping @MainActor @Sendable (Int32) -> Void
    ) {
        process.executableURL = command.executableURL
        process.arguments = command.arguments
        process.environment = command.environment
        process.standardOutput = outputPipe
        process.standardError = FileHandle.standardError
        let outputLines = OutputLines()
        outputPipe.fileHandleForReading.readabilityHandler = { outputHandle in
            let newBytes = outputHandle.availableData
            guard !newBytes.isEmpty else {
                return
            }
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
