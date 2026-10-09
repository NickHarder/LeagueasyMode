import Foundation

/// A callout the overlay page hands the app to speak (`overlay/web/src/speech.ts`), when the
/// player turned speech on in the settings.
public enum SpokenCallout {
    /// The name the page posts its message to: `window.webkit.messageHandlers.<name>`.
    public static let messageName = "leagueasymodeSpeak"
    /// The longest text spoken; a callout is a short line.
    static let longestText = 200

    /// Returns the text to speak from what the page sent.
    ///
    /// - Parameter body: The message's body.
    /// - Returns: The text, trimmed, or nil when the body is not a short line of text.
    public static func text(fromMessageBody body: Any) -> String? {
        guard let text = (body as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
            !text.isEmpty,
            text.count <= longestText
        else {
            return nil
        }
        return text
    }
}
