import CoreGraphics
import Foundation

/// Where the overlay page has buttons the player can click, the "Click to mark spells" setting's
/// (`overlay/web/src/marking.ts`). The panel lets every click through to the game but those on a
/// button: it takes the mouse only while the pointer is over one, and never the keyboard.
public enum ClickRegions {
    /// The name the page posts its message to: `window.webkit.messageHandlers.<name>`.
    public static let messageName = "leagueasymodeClickRegions"
    /// The most buttons a page has: three on each of five enemies' rows, with room to spare.
    static let mostRegions = 64

    /// Returns the buttons' rectangles from what the page sent.
    ///
    /// - Parameter body: The message's body: JSON text, a list of `[left, top, width, height]` in
    ///   the page's points from its top left.
    /// - Returns: The rectangles, empty when there are none, or nil when the body is anything else.
    public static func rectangles(fromMessageBody body: Any) -> [CGRect]? {
        guard
            let text = body as? String,
            let lists = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [[Double]],
            lists.count <= mostRegions
        else {
            return nil
        }
        var rectangles: [CGRect] = []
        for list in lists {
            guard list.count == 4, list[2] > 0, list[3] > 0, list.allSatisfy(\.isFinite) else {
                return nil
            }
            rectangles.append(CGRect(x: list[0], y: list[1], width: list[2], height: list[3]))
        }
        return rectangles
    }

    /// Returns whether the pointer is over a button.
    ///
    /// - Parameters:
    ///   - rectangles: The buttons, in the page's points from its top left.
    ///   - pointInWindow: The pointer, in the panel's points from its bottom left, as AppKit has it.
    ///   - windowHeight: The panel's height, which turns one origin into the other.
    /// - Returns: Whether a button is under the pointer.
    public static func contains(_ rectangles: [CGRect], pointInWindow: CGPoint, windowHeight: CGFloat) -> Bool {
        let pointInPage = CGPoint(x: pointInWindow.x, y: windowHeight - pointInWindow.y)
        return rectangles.contains { $0.contains(pointInPage) }
    }
}
