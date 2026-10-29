import Foundation

/// Reads the line `leagueasymode run` prints once its local server is up:
/// `LEAGUEASYMODE_OVERLAY_URL=http://127.0.0.1:<port>/`.
public enum EngineAnnouncement {
    /// What the line starts with; the overlay page's address follows it.
    public static let linePrefix = "LEAGUEASYMODE_OVERLAY_URL="

    /// The only host the overlay page may be loaded from.
    public static let localHost = "127.0.0.1"

    /// Returns the overlay page's address from one line of the engine's output.
    ///
    /// - Parameter outputLine: One line the engine printed, with or without its newline.
    /// - Returns: The address, or nil for any other line and for an address that is not plain
    ///   HTTP on 127.0.0.1, which the engine never announces.
    public static func overlayURL(fromLine outputLine: String) -> URL? {
        let trimmedLine = outputLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedLine.hasPrefix(linePrefix) else {
            return nil
        }
        let addressText = String(trimmedLine.dropFirst(linePrefix.count))
        guard
            let components = URLComponents(string: addressText),
            components.scheme == "http",
            components.host == localHost,
            components.port != nil
        else {
            return nil
        }
        return components.url
    }

    /// What the line the engine prints when a game's case is kept starts with; the game's id
    /// follows it.
    public static let caseReadyPrefix = "LEAGUEASYMODE_CASE_READY="

    /// Returns the id of the game whose case the engine has just kept.
    ///
    /// - Parameter outputLine: One line the engine printed, with or without its newline.
    /// - Returns: The game's id, or nil for any other line and for an id that is not a positive
    ///   whole number, which the engine never announces.
    public static func caseReadyGameID(fromLine outputLine: String) -> Int64? {
        let trimmedLine = outputLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedLine.hasPrefix(caseReadyPrefix) else {
            return nil
        }
        guard let gameID = Int64(trimmedLine.dropFirst(caseReadyPrefix.count)), gameID > 0 else {
            return nil
        }
        return gameID
    }
}

/// Opens the roast once for each game: the engine announces a game's case when the quick case is
/// kept and again when the full one replaces it, and the page already open picks up the full one.
public struct RoastOpening: Sendable {
    private var lastOpenedGameID: Int64?

    public init() {}

    /// Returns whether to open the roast for a game whose case was just kept, and notes it.
    ///
    /// - Parameter gameID: The game's id, as the engine announced it.
    /// - Returns: True the first time for each game in a row, false after.
    public mutating func shouldOpen(gameID: Int64) -> Bool {
        guard gameID != lastOpenedGameID else {
            return false
        }
        lastOpenedGameID = gameID
        return true
    }
}
