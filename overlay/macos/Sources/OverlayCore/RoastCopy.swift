import Foundation

/// Which take the copy shortcut asks for (phase 11.4): ⌃⌥C copies the closing line the post-game
/// window shows, and pressed again within a few seconds, the take after it, then the one after.
///
/// Nothing is ever sent to chat: the app puts the line on the clipboard, and the player pastes it.
public struct CopyPresses: Sendable {
    /// How soon after a press another one asks for the next take.
    public static let againWithinSeconds: Double = 5

    private var lastPressSeconds: Double?
    private var laterTakes = 0

    public init() {}

    /// Counts a press.
    ///
    /// - Parameter atSeconds: When the key was pressed, on any steady clock.
    /// - Returns: How many takes after the shown one to copy: 0 for a first press, one more for each
    ///   press within `againWithinSeconds` of the press before it.
    public mutating func press(atSeconds: Double) -> Int {
        let secondsSinceLastPress = lastPressSeconds.map { atSeconds - $0 }
        if let secondsSinceLastPress, (0...Self.againWithinSeconds).contains(secondsSinceLastPress) {
            laterTakes += 1
        } else {
            laterTakes = 0
        }
        lastPressSeconds = atSeconds
        return laterTakes
    }
}

/// The request for the line to copy, from the engine's `/closing-line`.
public enum ClosingLineRequest {
    /// Returns the request.
    ///
    /// - Parameters:
    ///   - overlayURL: The overlay page's address, as the engine announced it.
    ///   - laterTakes: How many takes after the shown one (`CopyPresses`).
    /// - Returns: The request.
    public static func make(overlayURL: URL, laterTakes: Int) -> URLRequest {
        let lineURL = overlayURL.appendingPathComponent("closing-line")
        var components = URLComponents(url: lineURL, resolvingAgainstBaseURL: false)
        components?.queryItems = [URLQueryItem(name: "next", value: String(laterTakes))]
        return URLRequest(url: components?.url ?? lineURL)
    }
}

/// The line the engine gives to copy, and which take it is.
public struct CopiedLine: Decodable, Equatable, Sendable {
    public let text: String
    public let take: Int

    public init(text: String, take: Int) {
        self.text = text
        self.take = take
    }
}

/// What the shortcut does with the engine's answer, and what its toast says.
public enum CopyOutcome {
    /// How much of the line the toast shows.
    public static let toastCharacters = 60
    public static let engineNotRunningText = "Nothing copied: the engine is not running"

    /// Returns the line to copy from the engine's answer.
    ///
    /// - Parameters:
    ///   - statusCode: The answer's HTTP status.
    ///   - body: The answer.
    /// - Returns: The line, or nil when the answer gives none to copy.
    public static func line(statusCode: Int, body: Data) -> CopiedLine? {
        guard
            statusCode == 200,
            let line = try? JSONDecoder().decode(CopiedLine.self, from: body),
            !line.text.isEmpty
        else {
            return nil
        }
        return line
    }

    /// Returns the toast for a copied line: "Copied: " and the line, cut short with "…".
    public static func toastText(copied line: CopiedLine) -> String {
        let shownText =
            line.text.count > toastCharacters
            ? String(line.text.prefix(toastCharacters - 1)) + "…"
            : line.text
        return "Copied: \(shownText)"
    }

    /// Returns the toast when nothing was copied, by the engine's answer.
    public static func toastText(failedWith statusCode: Int) -> String {
        switch statusCode {
        case 200:
            return "Nothing copied: the engine's answer could not be read"
        case 404:
            return "Nothing to copy: no case for the last game yet"
        case 409:
            return "Nothing to copy during a game yet"
        default:
            return "Nothing copied: the engine answered HTTP \(statusCode)"
        }
    }
}
