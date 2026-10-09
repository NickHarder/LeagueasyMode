import CoreGraphics
import Foundation

/// A window on screen, as the window server lists it (`CGWindowListCopyWindowInfo`). Its owner's
/// name, bounds and layer need no permission; only its title would need Screen Recording.
public struct ListedWindow: Equatable, Sendable {
    /// The name of the app that owns it.
    public let ownerName: String
    /// Its bounds in the window server's coordinates: from the main screen's top left, y down.
    public let bounds: CGRect
    /// Its layer: 0 for an app's ordinary windows.
    public let layer: Int

    public init(ownerName: String, bounds: CGRect, layer: Int) {
        self.ownerName = ownerName
        self.bounds = bounds
        self.layer = layer
    }

    /// Reads one entry of the window server's list.
    ///
    /// - Parameter windowInfo: The entry.
    /// - Returns: The window, or nil when the entry lacks its owner's name or its bounds.
    public init?(windowInfo: [String: Any]) {
        guard
            let ownerName = windowInfo[kCGWindowOwnerName as String] as? String,
            let boundsDictionary = windowInfo[kCGWindowBounds as String] as? NSDictionary,
            let bounds = CGRect(dictionaryRepresentation: boundsDictionary as CFDictionary)
        else {
            return nil
        }
        self.init(
            ownerName: ownerName,
            bounds: bounds,
            layer: (windowInfo[kCGWindowLayer as String] as? Int) ?? 0
        )
    }
}

/// Where the overlay goes: over the screen or the window League shows, or else the main screen.
public enum GamePlacement: Equatable, Sendable {
    /// League fills a screen, full screen or borderless: the overlay covers that screen.
    case screen(CGRect)
    /// League is in a window: the overlay covers the window below its title bar, where League
    /// draws, so the minimap layer lines up there too.
    case window(CGRect)
    /// No window of League's is on screen: the overlay covers the main screen.
    case mainScreen(CGRect)

    /// The overlay's frame, in AppKit's coordinates.
    public var frame: CGRect {
        switch self {
        case .screen(let frame), .window(let frame), .mainScreen(let frame): frame
        }
    }

    /// What the menu says was found.
    public var menuText: String {
        switch self {
        case .screen(let frame): "League: full screen, \(Self.sizeText(frame))"
        case .window(let frame): "League: windowed, \(Self.sizeText(frame))"
        case .mainScreen: "League: no game window seen"
        }
    }

    private static func sizeText(_ frame: CGRect) -> String {
        "\(Int(frame.width.rounded())) \u{00d7} \(Int(frame.height.rounded()))"
    }
}

/// Finds League's game window among the windows on screen, and where the overlay goes over it.
public enum GameWindowLocator {
    /// The game's owner name, without spaces or case: "League of Legends" or "LeagueofLegends".
    /// The client, "LeagueClientUx", is not the game.
    static let gameOwnerName = "leagueoflegends"
    /// A window within this many points of each edge of its screen fills it.
    static let fillTolerance: CGFloat = 2

    /// Returns League's game window: its largest ordinary window on screen.
    ///
    /// - Parameter windows: The windows on screen.
    /// - Returns: The game's window, or nil when none is on screen.
    public static func gameWindow(in windows: [ListedWindow]) -> ListedWindow? {
        windows
            .filter { window in
                window.layer == 0
                    && normalizedName(window.ownerName) == gameOwnerName
                    && window.bounds.width > 0 && window.bounds.height > 0
            }
            .max { first, second in
                first.bounds.width * first.bounds.height < second.bounds.width * second.bounds.height
            }
    }

    /// Returns where the overlay goes.
    ///
    /// - Parameters:
    ///   - gameWindow: League's game window, or nil.
    ///   - screenFrames: Each screen's frame in AppKit's coordinates, the main screen first.
    ///   - titleBarHeight: The height of a titled window's title bar, which a windowed game has.
    /// - Returns: The placement.
    public static func placement(
        gameWindow: ListedWindow?, screenFrames: [CGRect], titleBarHeight: CGFloat
    ) -> GamePlacement {
        let mainScreenFrame = screenFrames.first ?? CGRect(x: 0, y: 0, width: 1440, height: 900)
        guard let gameWindow else {
            return .mainScreen(mainScreenFrame)
        }
        // The window server counts down from the main screen's top; AppKit counts up from its
        // bottom.
        let gameFrame = CGRect(
            x: gameWindow.bounds.minX,
            y: mainScreenFrame.maxY - gameWindow.bounds.maxY,
            width: gameWindow.bounds.width,
            height: gameWindow.bounds.height
        )
        let screenArea = { (screenFrame: CGRect) -> CGFloat in
            let overlap = screenFrame.intersection(gameFrame)
            return overlap.isNull ? 0 : overlap.width * overlap.height
        }
        guard
            let gameScreenFrame = screenFrames.max(by: { screenArea($0) < screenArea($1) }),
            screenArea(gameScreenFrame) > 0
        else {
            return .mainScreen(mainScreenFrame)
        }
        if gameFrame.insetBy(dx: -fillTolerance, dy: -fillTolerance).contains(gameScreenFrame) {
            return .screen(gameScreenFrame)
        }
        let hasRoomForTitleBar = gameFrame.height > titleBarHeight * 2
        return .window(
            CGRect(
                x: gameFrame.minX,
                y: gameFrame.minY,
                width: gameFrame.width,
                height: hasRoomForTitleBar ? gameFrame.height - titleBarHeight : gameFrame.height
            )
        )
    }

    private static func normalizedName(_ name: String) -> String {
        name.lowercased().filter { !$0.isWhitespace }
    }
}
