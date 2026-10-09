import Foundation

/// A release's version, as a tag names it (`v1.4.2`): up to three numbers, the missing ones nought.
public struct ReleaseVersion: Comparable, Sendable, CustomStringConvertible {
    /// The major, minor and patch numbers.
    public let numbers: [Int]

    static let numberCount = 3

    /// Reads a version, with or without its `v`.
    ///
    /// - Parameter text: The tag or version, such as `v1.4.2` or `1.4`.
    /// - Returns: The version, or nil when the text is anything but one to three numbers.
    public init?(_ text: String) {
        let versionText = text.hasPrefix("v") ? text.dropFirst() : Substring(text)
        let parts = versionText.split(separator: ".", omittingEmptySubsequences: false)
        guard (1...Self.numberCount).contains(parts.count) else {
            return nil
        }
        var readNumbers: [Int] = []
        for part in parts {
            guard
                !part.isEmpty,
                part.allSatisfy({ $0.isASCII && $0.isNumber }),
                let number = Int(part)
            else {
                return nil
            }
            readNumbers.append(number)
        }
        numbers = readNumbers + Array(repeating: 0, count: Self.numberCount - readNumbers.count)
    }

    public static func < (lhs: ReleaseVersion, rhs: ReleaseVersion) -> Bool {
        lhs.numbers.lexicographicallyPrecedes(rhs.numbers)
    }

    public var description: String {
        numbers.map(String.init).joined(separator: ".")
    }
}

/// A release newer than the app, which the menu offers.
public struct AvailableRelease: Equatable, Sendable {
    /// Its version.
    public let version: ReleaseVersion
    /// Its page on GitHub, which holds the zipped app.
    public let pageURL: URL

    /// The menu item that opens its page.
    public var menuTitle: String {
        "LeagueasyMode \(version) is out\u{2026}"
    }
}

/// Whether a newer release is out: GitHub's latest release of this repository, asked at most once a
/// day. It is the app's only request beyond this Mac, League's servers and Data Dragon, and a switch
/// in the menu turns it off.
public enum UpdateCheck {
    /// The repository whose releases hold the app.
    public static let repository = "NickHarder/LeagueasyMode"
    /// How long after one check the next is due: a day.
    public static let interval: TimeInterval = 24 * 60 * 60

    static let requestTimeoutSeconds: TimeInterval = 30
    static let latestReleaseURL = URL(string: "https://api.github.com/repos/\(repository)/releases/latest")!

    /// Whether a check is due.
    ///
    /// - Parameters:
    ///   - lastCheckedAt: When the app last asked, or nil when it never has.
    ///   - now: The time now.
    /// - Returns: True when it never asked, or asked a day or more ago; also when the last check
    ///   seems to be in the future, as after the clock was set back, so that checks do not stop.
    public static func isDue(lastCheckedAt: Date?, now: Date) -> Bool {
        guard let lastCheckedAt else {
            return true
        }
        return now < lastCheckedAt || now.timeIntervalSince(lastCheckedAt) >= interval
    }

    /// Returns the request for the latest release, from GitHub's API without a token.
    ///
    /// - Parameter appVersion: The app's version, which names it to GitHub.
    /// - Returns: The request.
    public static func request(appVersion: ReleaseVersion) -> URLRequest {
        var request = URLRequest(url: latestReleaseURL, timeoutInterval: requestTimeoutSeconds)
        request.httpMethod = "GET"
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        request.setValue("LeagueasyMode/\(appVersion)", forHTTPHeaderField: "User-Agent")
        return request
    }

    /// Reads GitHub's answer for a release newer than the app.
    ///
    /// The release's page is always built from its tag on this repository, whatever address the
    /// answer gives, so the menu only ever opens GitHub's page of a release of LeagueasyMode.
    ///
    /// - Parameters:
    ///   - answer: The body of GitHub's answer.
    ///   - appVersion: The app's version.
    /// - Returns: The release, or nil when the answer is no published release, its tag no version,
    ///   or it is not newer than the app.
    public static func newerRelease(answer: Data, appVersion: ReleaseVersion) -> AvailableRelease? {
        guard
            let release = try? JSONDecoder().decode(LatestReleaseAnswer.self, from: answer),
            release.draft != true,
            release.prerelease != true,
            let version = ReleaseVersion(release.tagName),
            appVersion < version,
            let pageURL = URL(string: "https://github.com/\(repository)/releases/tag/\(release.tagName)")
        else {
            return nil
        }
        return AvailableRelease(version: version, pageURL: pageURL)
    }
}

/// The fields of GitHub's latest release that the check reads.
private struct LatestReleaseAnswer: Decodable {
    let tagName: String
    let draft: Bool?
    let prerelease: Bool?

    enum CodingKeys: String, CodingKey {
        case tagName = "tag_name"
        case draft
        case prerelease
    }
}
