import CoreGraphics
import Foundation

/// The key that shows the overlay's details while it is held: Tab, as League's scoreboard, or
/// Option. At a glance the overlay shows the timers, the newest callouts and one short line an
/// enemy; held, the rest (`overlay/web/src/overlay.ts`). The app only reads whether the key is
/// down, as the Mac reports it; it never takes the key from the game, nor presses one.
public enum DetailsKey {
    /// The Tab key's code, the same on every Mac keyboard layout.
    public static let tabKeyCode: CGKeyCode = 48
    /// How often the app looks whether the key is held: 20 times a second, so the details show
    /// within a frame or two of pressing it.
    public static let checkSeconds: TimeInterval = 1.0 / 20

    /// Returns whether the details show, from the keys held now.
    ///
    /// - Parameters:
    ///   - isOptionDown: Whether Option is held, alone or with other modifiers.
    ///   - isTabDown: Whether Tab is held.
    /// - Returns: Whether either is.
    public static func isHeld(isOptionDown: Bool, isTabDown: Bool) -> Bool {
        isOptionDown || isTabDown
    }

    /// Tells the page the key is held, or let go. The `?.` leaves an older page as it is.
    ///
    /// - Parameter isHeld: Whether the key is held.
    /// - Returns: The script.
    public static func script(isHeld: Bool) -> String {
        "window.leagueasymodeSetDetailsHeld?.(\(isHeld));"
    }
}

/// Tells the page only when the key's state changes, not 20 times a second.
public struct DetailsKeyWatcher: Sendable {
    private var lastHeld: Bool?

    public init() {}

    /// Returns the script to run for the keys held now, or nil when nothing changed.
    ///
    /// - Parameters:
    ///   - isOptionDown: Whether Option is held.
    ///   - isTabDown: Whether Tab is held.
    /// - Returns: The script, or nil.
    public mutating func scriptForChange(isOptionDown: Bool, isTabDown: Bool) -> String? {
        let isHeld = DetailsKey.isHeld(isOptionDown: isOptionDown, isTabDown: isTabDown)
        guard isHeld != lastHeld else {
            return nil
        }
        lastHeld = isHeld
        return DetailsKey.script(isHeld: isHeld)
    }

    /// Forgets what the page was told, as when it loads again and knows nothing.
    public mutating func forget() {
        lastHeld = nil
    }
}
