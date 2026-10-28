import Foundation

/// The overlay gives the keyboard back to the game whenever it finds itself holding it outside
/// edit mode; the menu says how often, so that a test on a Mac shows whether it happens.
public enum KeyboardHandBack {
    /// The menu's line for how often the keyboard was handed back.
    ///
    /// - Parameter handBackCount: How many times, since the app started.
    /// - Returns: The line; nil when it never happened.
    public static func menuText(handBackCount: Int) -> String? {
        switch handBackCount {
        case ..<1: nil
        case 1: "Keyboard: handed back to the game once"
        default: "Keyboard: handed back to the game \(handBackCount) times"
        }
    }
}
