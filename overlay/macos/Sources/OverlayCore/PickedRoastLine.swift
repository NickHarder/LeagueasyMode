import Foundation

/// A line for chat the player clicked on the overlay's roast card after a game
/// (`overlay/web/src/roast_card.ts`); the app copies it and says so in its toast.
public enum PickedRoastLine {
    /// The name the page posts its message to: `window.webkit.messageHandlers.<name>`.
    public static let messageName = "leagueasymodeCopy"
    /// The longest line copied: a chat line is far shorter.
    static let longestText = 500

    /// Returns the line to copy from what the page sent.
    ///
    /// - Parameter body: The message's body.
    /// - Returns: The line, trimmed, or nil when the body is not a line of text.
    public static func text(fromMessageBody body: Any) -> String? {
        guard let text = (body as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
            !text.isEmpty,
            text.count <= longestText,
            !text.contains("\n")
        else {
            return nil
        }
        return text
    }
}
