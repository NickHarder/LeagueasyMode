import ServiceManagement

/// The menu's "Open at login": whether macOS opens the app when the player logs in, from what
/// `SMAppService.mainApp` says.
public enum LoginItemState: Equatable, Sendable {
    /// macOS opens the app at login.
    case on
    /// It does not.
    case off
    /// The app asked, and the player is still to allow it in System Settings, Login Items.
    case needsApproval
    /// The app is not a bundle, as when run from a clone with `swift run`, so it cannot be a login
    /// item: the menu leaves the item out.
    case unavailable

    /// Reads the system's answer.
    ///
    /// - Parameters:
    ///   - status: `SMAppService.mainApp.status`.
    ///   - isBundledApp: Whether the app runs from `LeagueasyMode.app`.
    public init(status: SMAppService.Status, isBundledApp: Bool) {
        guard isBundledApp else {
            self = .unavailable
            return
        }
        switch status {
        case .enabled:
            self = .on
        case .requiresApproval:
            self = .needsApproval
        case .notRegistered, .notFound:
            self = .off
        @unknown default:
            self = .off
        }
    }

    /// The menu item's title.
    public var menuTitle: String {
        switch self {
        case .needsApproval: "Open at login (allow in System Settings\u{2026})"
        case .on, .off, .unavailable: "Open at login"
        }
    }

    /// Whether the menu item shows a check mark: the player has asked for it.
    public var isChecked: Bool {
        self == .on || self == .needsApproval
    }
}
