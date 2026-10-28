import Foundation
import OverlayCore

/// Puts a build CI published (`BuildUpdateCheck`) in place of the running app: it downloads the
/// zip and its checksum, checks one against the other, unpacks the app, checks it is LeagueasyMode
/// and that its signature holds, and replaces the running app with it. The app then starts the new
/// one and quits.
///
/// A file the app downloads itself is not marked as from the internet, so the new build opens
/// without macOS's "Open Anyway".
enum UpdateInstaller {
    /// Why a build was not installed, in the menu's words.
    enum InstallError: LocalizedError {
        case download(statusCode: Int)
        case checksum
        case notTheApp
        case notWritable
        case tool(name: String, exitStatus: Int32)

        var errorDescription: String? {
            switch self {
            case let .download(statusCode): "the download failed (HTTP \(statusCode))"
            case .checksum: "the download does not match its checksum"
            case .notTheApp: "the download is not LeagueasyMode"
            case .notWritable: "the app's folder cannot be written; download it from the release page"
            case let .tool(name, exitStatus): "\(name) failed (exit \(exitStatus))"
            }
        }
    }

    /// Downloads, checks and unpacks a build, then puts it where the running app is.
    ///
    /// - Parameters:
    ///   - build: The build.
    ///   - appURL: The running app, which the build replaces.
    /// - Throws: An `InstallError`, or the error of a download or of a file operation; the running
    ///   app is left as it was unless the last step, the replacement, succeeded.
    static func install(_ build: AvailableBuild, over appURL: URL) async throws {
        let archiveData = try await download(build.archiveURL)
        let checksumData = try await download(build.checksumURL)
        let archiveName = build.archiveURL.lastPathComponent
        guard
            let expectedDigest = ArchiveChecksum.expectedDigest(
                checksumFile: String(decoding: checksumData, as: UTF8.self), archiveName: archiveName
            ),
            ArchiveChecksum.sha256Hex(of: archiveData) == expectedDigest
        else {
            throw InstallError.checksum
        }
        guard FileManager.default.isWritableFile(atPath: appURL.deletingLastPathComponent().path) else {
            throw InstallError.notWritable
        }
        // On the app's own volume, so that the replacement is a move.
        let workDirectory = try FileManager.default.url(
            for: .itemReplacementDirectory, in: .userDomainMask, appropriateFor: appURL, create: true
        )
        defer { try? FileManager.default.removeItem(at: workDirectory) }
        let archiveURL = workDirectory.appendingPathComponent(archiveName)
        try archiveData.write(to: archiveURL)
        let unpackedDirectory = workDirectory.appendingPathComponent("unpacked", isDirectory: true)
        try run("/usr/bin/ditto", ["-x", "-k", archiveURL.path, unpackedDirectory.path])
        let newAppURL = unpackedDirectory.appendingPathComponent("LeagueasyMode.app", isDirectory: true)
        guard
            let newIdentifier = Bundle(url: newAppURL)?.bundleIdentifier,
            newIdentifier == Bundle.main.bundleIdentifier
        else {
            throw InstallError.notTheApp
        }
        try run("/usr/bin/codesign", ["--verify", "--strict", "--deep", newAppURL.path])
        _ = try FileManager.default.replaceItemAt(appURL, withItemAt: newAppURL)
    }

    /// Starts the app at an address a moment from now, once this one has quit.
    ///
    /// - Parameter appURL: The app.
    /// - Throws: The error `Process.run` gives when the shell cannot be started.
    static func startAgain(_ appURL: URL) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = ["-c", "sleep 2; /usr/bin/open \"$0\"", appURL.path]
        try process.run()
    }

    private static func download(_ url: URL) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(from: url)
        let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard statusCode == 200 else {
            throw InstallError.download(statusCode: statusCode)
        }
        return data
    }

    private static func run(_ toolPath: String, _ arguments: [String]) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: toolPath)
        process.arguments = arguments
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw InstallError.tool(name: URL(fileURLWithPath: toolPath).lastPathComponent, exitStatus: process.terminationStatus)
        }
    }
}
