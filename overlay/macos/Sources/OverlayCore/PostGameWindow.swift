import Foundation

/// The post-game window: the last game reconstructed, a page the engine serves beside the overlay.
public enum PostGameWindow {
    /// The page's path, beside the overlay page.
    public static let pagePath = "summary.html"

    /// Returns the post-game window's address.
    ///
    /// - Parameter overlayURL: The overlay page's address, as the engine announced it.
    /// - Returns: The page's address on the same server.
    public static func pageURL(overlayURL: URL) -> URL? {
        URL(string: pagePath, relativeTo: overlayURL)?.absoluteURL
    }
}
