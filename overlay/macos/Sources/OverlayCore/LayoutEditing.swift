import Foundation

/// What the app tells the overlay page about edit mode, as JavaScript its web view runs. The page
/// (`overlay/web/src/layout.ts`) defines the two functions; the `?.` leaves a page that does not,
/// such as an older engine's, as it is.
public enum LayoutEditing {
    /// Turns the page's edit mode on or off: its widgets outlined, named and draggable.
    ///
    /// - Parameter isEditing: Whether edit mode is on.
    /// - Returns: The script.
    public static func editingScript(isEditing: Bool) -> String {
        "window.leagueasymodeSetEditing?.(\(isEditing));"
    }

    /// Puts every widget back in its usual place, and has the engine keep that.
    public static let resetScript = "window.leagueasymodeResetLayout?.();"

    /// How long edit mode lasts before it ends by itself. While it is on, the overlay catches every
    /// click over the game, so it must never be left on by mistake.
    public static let timeLimit: TimeInterval = 120

    /// The key that ends edit mode: Escape, whose code is the same on every Mac keyboard layout.
    public static let escapeKeyCode: UInt16 = 53

    /// Returns whether edit mode, turned on at a time, has run its time.
    ///
    /// - Parameters:
    ///   - startedAt: When it was turned on.
    ///   - now: The time now.
    /// - Returns: Whether it should end.
    public static func hasRunOut(startedAt: Date, now: Date) -> Bool {
        now.timeIntervalSince(startedAt) >= timeLimit
    }

    /// Returns whether a key pressed in edit mode ends it.
    ///
    /// - Parameter keyCode: The key's code.
    /// - Returns: Whether it is Escape.
    public static func endsEditing(keyCode: UInt16) -> Bool {
        keyCode == escapeKeyCode
    }
}
