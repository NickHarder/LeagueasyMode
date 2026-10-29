import Foundation

/// A page the engine serves beside the overlay, which the app opens in a normal browser window.
public enum EnginePage: String, CaseIterable, Sendable {
    /// The shortcuts, the widgets and the menu, and what to do when something goes wrong; the app
    /// opens it once by itself, on its first start.
    case howToUse = "how-to-use.html"
    /// The post-game window: the last game reconstructed.
    case lastGame = "summary.html"
    /// What the overlay shows.
    case settings = "settings.html"
    /// What the engine sees, part by part, and the report to send after a test.
    case status = "status.html"

    /// The menu item that opens the page.
    public var menuTitle: String {
        switch self {
        case .howToUse: "How to use\u{2026}"
        case .lastGame: "Last game\u{2026}"
        case .settings: "Settings\u{2026}"
        case .status: "Status\u{2026}"
        }
    }

    /// Returns the page's address.
    ///
    /// - Parameter overlayURL: The overlay page's address, as the engine announced it.
    /// - Returns: The page's address on the same server.
    public func url(overlayURL: URL) -> URL? {
        URL(string: rawValue, relativeTo: overlayURL)?.absoluteURL
    }
}
