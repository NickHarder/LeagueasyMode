import Foundation

/// Whether the overlay page is showing in the overlay's window, as the menu says it: the first
/// thing to look at when the overlay shows nothing over the game.
public enum OverlayPageState: Equatable, Sendable {
    /// The engine has not yet said where the page is.
    case waiting
    /// The page is being loaded from the engine.
    case loading
    /// The page has loaded.
    case loaded
    /// The page did not load, for the reason the web view gave.
    case failed(String)

    /// The menu's line for the state.
    public var menuText: String {
        switch self {
        case .waiting: "Overlay: waiting for the engine"
        case .loading: "Overlay: loading the page\u{2026}"
        case .loaded: "Overlay: page loaded"
        case .failed(let reason): "Overlay: the page did not load (\(reason))"
        }
    }
}
