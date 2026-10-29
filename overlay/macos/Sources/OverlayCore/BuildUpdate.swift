import CryptoKit
import Foundation

/// A build newer than the app that CI published from `main` as a prerelease (`build-<number>`), which
/// the menu offers to install.
public struct AvailableBuild: Equatable, Sendable {
    /// CI's run number, which orders builds.
    public let buildNumber: Int
    /// The version the build carries.
    public let version: ReleaseVersion
    /// The zipped app.
    public let archiveURL: URL
    /// Its SHA-256, as `shasum -a 256` writes it.
    public let checksumURL: URL
    /// The prerelease's page on GitHub.
    public let pageURL: URL

    /// The menu item that installs it.
    public var menuTitle: String {
        "Install update: build \(buildNumber) (\(version))\u{2026}"
    }
}

/// Whether CI published a build newer than the app: the repository's newest releases, of which the
/// prereleases tagged `build-<number>` are the builds of `main`, each with its zip and checksum.
///
/// Before, every build took a new link, a download, an unzip and "Open Anyway"; the app now finds
/// the build itself, and `UpdateInstaller` puts it in place.
public enum BuildUpdateCheck {
    static let tagPrefix = "build-"
    static let releaseCount = 30
    static let releasesURL = URL(
        string: "https://api.github.com/repos/\(UpdateCheck.repository)/releases?per_page=\(releaseCount)"
    )!

    /// Returns the request for the newest releases, from GitHub's API without a token.
    ///
    /// - Parameter appVersion: The app's version, which names it to GitHub.
    /// - Returns: The request.
    public static func request(appVersion: ReleaseVersion) -> URLRequest {
        var request = URLRequest(url: releasesURL, timeoutInterval: UpdateCheck.requestTimeoutSeconds)
        request.httpMethod = "GET"
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        request.setValue("LeagueasyMode/\(appVersion)", forHTTPHeaderField: "User-Agent")
        return request
    }

    /// Reads GitHub's answer for the newest build after the app's.
    ///
    /// A build is newer when its number is higher and its version no lower. Its addresses are always
    /// built from its tag and its files' names on this repository, whatever the answer gives, so the
    /// app only ever downloads a build of LeagueasyMode.
    ///
    /// - Parameters:
    ///   - answer: The body of GitHub's answer.
    ///   - appVersion: The app's version.
    ///   - appBuildNumber: The app's build number; nil for a build CI did not number, for which
    ///     every published build is newer.
    /// - Returns: The newest build, or nil when there is none newer.
    public static func newerBuild(
        answer: Data, appVersion: ReleaseVersion, appBuildNumber: Int?
    ) -> AvailableBuild? {
        guard let releases = try? JSONDecoder().decode([ReleaseAnswer].self, from: answer) else {
            return nil
        }
        let builds = releases.compactMap { release -> AvailableBuild? in
            guard
                release.draft != true,
                release.prerelease == true,
                release.tagName.hasPrefix(tagPrefix),
                let buildNumber = Int(release.tagName.dropFirst(tagPrefix.count)),
                let archiveName = release.assets.map(\.name).first(where: {
                    $0.hasPrefix("LeagueasyMode-") && $0.hasSuffix("-build-\(buildNumber).zip")
                }),
                release.assets.contains(where: { $0.name == archiveName + ".sha256" }),
                let version = ReleaseVersion(
                    String(archiveName.dropFirst("LeagueasyMode-".count).dropLast("-build-\(buildNumber).zip".count))
                ),
                let pageURL = URL(string: "https://github.com/\(UpdateCheck.repository)/releases/tag/\(release.tagName)"),
                let archiveURL = downloadURL(tag: release.tagName, fileName: archiveName),
                let checksumURL = downloadURL(tag: release.tagName, fileName: archiveName + ".sha256")
            else {
                return nil
            }
            return AvailableBuild(
                buildNumber: buildNumber,
                version: version,
                archiveURL: archiveURL,
                checksumURL: checksumURL,
                pageURL: pageURL
            )
        }
        return builds
            .filter { build in
                build.version >= appVersion && appBuildNumber.map { build.buildNumber > $0 } ?? true
            }
            .max { $0.buildNumber < $1.buildNumber }
    }

    /// The address of a file of a release of this repository.
    static func downloadURL(tag: String, fileName: String) -> URL? {
        URL(string: "https://github.com/\(UpdateCheck.repository)/releases/download/\(tag)/\(fileName)")
    }
}

/// Checks a downloaded build against the SHA-256 published beside it.
public enum ArchiveChecksum {
    /// Returns the digest a checksum file gives for an archive.
    ///
    /// - Parameters:
    ///   - checksumFile: The file, as `shasum -a 256` writes it: the digest, two spaces, the name.
    ///   - archiveName: The archive's name.
    /// - Returns: The digest in lowercase hexadecimal, or nil when the file names another archive or
    ///   holds no digest.
    public static func expectedDigest(checksumFile: String, archiveName: String) -> String? {
        for line in checksumFile.split(whereSeparator: \.isNewline) {
            let fields = line.split(separator: " ", omittingEmptySubsequences: true)
            guard fields.count == 2 else {
                continue
            }
            let digest = fields[0].lowercased()
            let name = fields[1].hasPrefix("*") ? String(fields[1].dropFirst()) : String(fields[1])
            if name == archiveName, digest.count == 64, digest.allSatisfy(\.isHexDigit) {
                return digest
            }
        }
        return nil
    }

    /// Returns the SHA-256 of some bytes, in lowercase hexadecimal.
    ///
    /// - Parameter data: The bytes.
    /// - Returns: The digest.
    public static func sha256Hex(of data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}

/// The fields of one of GitHub's releases that the check reads.
private struct ReleaseAnswer: Decodable {
    let tagName: String
    let draft: Bool?
    let prerelease: Bool?
    let assets: [AssetAnswer]

    enum CodingKeys: String, CodingKey {
        case tagName = "tag_name"
        case draft
        case prerelease
        case assets
    }
}

/// A file of a release: only its name is read.
private struct AssetAnswer: Decodable {
    let name: String
}

/// When the app installs a newer build by itself: with the player's switch on, and never while
/// League's game runs, its window is on screen, the widgets are being moved, or an install is
/// running. Installing restarts the app, which would blank the overlay for a few seconds in a game
/// and split its recording in two; a game in another Space or behind another app has no window on
/// screen, so the game's process is asked too (the owner's game of 2026-10-29 22:02, cut in two by
/// build 222).
public enum AutomaticUpdate {
    /// Returns whether the app may install a build now, without asking.
    ///
    /// - Parameters:
    ///   - isOn: The player's switch, "Install updates automatically".
    ///   - placement: Where the overlay is; only `.mainScreen` means no game window is on screen.
    ///   - isGameRunning: Whether League's game app runs, on screen or not.
    ///   - isEditingLayout: Whether the widgets are being moved.
    ///   - isInstalling: Whether an install is already running.
    /// - Returns: Whether to install now.
    public static func canInstallNow(
        isOn: Bool, placement: GamePlacement?, isGameRunning: Bool, isEditingLayout: Bool, isInstalling: Bool
    ) -> Bool {
        guard isOn, !isGameRunning, !isEditingLayout, !isInstalling, case .some(.mainScreen) = placement else {
            return false
        }
        return true
    }
}

/// Where a new build goes. Usually where the running app is; but an app the browser downloaded
/// and that was opened where it was unzipped runs from a read-only copy macOS makes for it (App
/// Translocation), which nothing can replace: the build then goes to Applications. A build the app
/// downloads itself is not marked as from the internet, so it runs from where it is put.
public enum UpdateTarget {
    /// Where a translocated app's build goes.
    public static let applicationsAppURL = URL(fileURLWithPath: "/Applications/LeagueasyMode.app", isDirectory: true)

    /// Returns whether an app runs from the read-only copy macOS made for it.
    ///
    /// - Parameter appURL: The running app.
    /// - Returns: Whether its path is under macOS's translocation folder.
    public static func isTranslocated(_ appURL: URL) -> Bool {
        appURL.path.contains("/AppTranslocation/")
    }

    /// Returns where a new build goes.
    ///
    /// - Parameter runningAppURL: The running app.
    /// - Returns: The running app, or Applications' LeagueasyMode.app for a translocated one.
    public static func installURL(runningAppURL: URL) -> URL {
        isTranslocated(runningAppURL) ? applicationsAppURL : runningAppURL
    }
}
