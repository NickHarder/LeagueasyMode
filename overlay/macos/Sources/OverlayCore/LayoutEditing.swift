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
}
