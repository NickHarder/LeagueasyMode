import AppKit

/// How high the overlay sits among windows. Which one stays above League depends on how League
/// draws (full screen, borderless or windowed), so the menu lets the player try each.
enum WindowLevelChoice: String, CaseIterable {
    case floating
    case statusBar
    case screenSaver
    case aboveCapturedDisplay

    /// The level the overlay starts at: above full-screen apps, below a captured display.
    static let initialChoice = WindowLevelChoice.screenSaver

    /// The menu's name for the level.
    var menuTitle: String {
        switch self {
        case .floating:
            return "Floating"
        case .statusBar:
            return "Status bar"
        case .screenSaver:
            return "Screen saver (default)"
        case .aboveCapturedDisplay:
            return "Above a captured display"
        }
    }

    /// The window level itself.
    var windowLevel: NSWindow.Level {
        switch self {
        case .floating:
            return .floating
        case .statusBar:
            return .statusBar
        case .screenSaver:
            return .screenSaver
        case .aboveCapturedDisplay:
            // A game that captures the display draws at the shielding level; one above it shows.
            return NSWindow.Level(rawValue: Int(CGShieldingWindowLevel()) + 1)
        }
    }
}
