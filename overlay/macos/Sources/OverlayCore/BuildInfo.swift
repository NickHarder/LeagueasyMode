import Foundation

/// Which build of the app is running: its version, CI's run number and the commit it was built
/// from, which `scripts/build_app.sh` writes into the bundle's Info.plist. Every build was "0.1.0"
/// before, so no one could tell which was running; the menu, the engine's status page and its
/// crash reports now name the build.
public struct BuildInfo: Equatable, Sendable {
    /// The key of the commit in the Info.plist.
    public static let commitKey = "LeagueasyModeCommit"

    public let version: String?
    public let buildNumber: String?
    public let commit: String?

    /// Reads the build from a bundle's Info.plist.
    ///
    /// - Parameter infoDictionary: The bundle's Info.plist; nil for an app run from its source.
    public init(infoDictionary: [String: Any]?) {
        version = infoDictionary?["CFBundleShortVersionString"] as? String
        buildNumber = infoDictionary?["CFBundleVersion"] as? String
        commit = infoDictionary?[Self.commitKey] as? String
    }

    /// CI's run number, which orders builds; nil for a build CI did not number.
    public var ciBuildNumber: Int? {
        buildNumber.flatMap { Int($0) }
    }

    /// The build in words: "0.1.0 (build 62, b0d63a8)", or "from source" without a version.
    public var label: String {
        guard let version else {
            return "from source"
        }
        // A bundle's build number is its version until CI gives it one of its own.
        let ownBuildNumber = buildNumber.flatMap { $0 == version ? nil : "build \($0)" }
        let details = [ownBuildNumber, commit].compactMap { $0 }
        return details.isEmpty ? version : "\(version) (\(details.joined(separator: ", ")))"
    }
}
