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
}
