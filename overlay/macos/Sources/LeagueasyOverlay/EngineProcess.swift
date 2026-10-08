import Foundation
import OverlayCore

/// Runs the engine (`leagueasymode run`) as a child process and reports what it announces.
///
/// The engine's standard output is read for the line with the overlay's address; its standard
/// error goes to the app's, so `swift run` shows the engine's log.
final class EngineProcess {
    private let process = Process()
    private let outputPipe = Pipe()
    private var lineBuffer = LineBuffer()

    /// Prepares the process; nothing runs until `start`.
    ///
    /// - Parameters:
    ///   - command: How to run the engine.
    ///   - onOverlayURL: Called on the main queue with the overlay's address, once the engine is up.
    ///   - onExit: Called on the main queue with the engine's exit status, when it stops.
    init(
        command: EngineCommand,
        onOverlayURL: @escaping @Sendable (URL) -> Void,
        onExit: @escaping @Sendable (Int32) -> Void
    ) {
        process.executableURL = command.executableURL
        process.arguments = command.arguments
        process.environment = command.environment
        process.standardOutput = outputPipe
        process.standardError = FileHandle.standardError
        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] outputHandle in
            let newBytes = outputHandle.availableData
            guard let self, !newBytes.isEmpty else {
                return
            }
            for outputLine in self.lineBuffer.append(newBytes) {
                if let overlayURL = EngineAnnouncement.overlayURL(fromLine: outputLine) {
                    DispatchQueue.main.async { onOverlayURL(overlayURL) }
                }
            }
        }
        process.terminationHandler = { finishedProcess in
            let exitStatus = finishedProcess.terminationStatus
            DispatchQueue.main.async { onExit(exitStatus) }
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
