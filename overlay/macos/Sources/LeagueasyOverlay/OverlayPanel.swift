import AppKit
import WebKit

/// A transparent window over League, its screen or its window, that shows the overlay page.
///
/// It never becomes key or main and its panel does not activate the app, so League keeps the
/// keyboard and the focus; clicks pass through it to the game. It joins every Space, the
/// full-screen ones included.
final class OverlayPanel: NSPanel {
    private let webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())

    /// Creates the panel over a screen, hidden until `showOverlay` is called.
    ///
    /// - Parameter screenFrame: The frame of the screen the game is on.
    convenience init(screenFrame: NSRect) {
        self.init(
            contentRect: screenFrame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        ignoresMouseEvents = true
        hidesOnDeactivate = false
        isReleasedWhenClosed = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        // WKWebView paints white behind a page unless told not to; the page itself is transparent.
        webView.setValue(false, forKey: "drawsBackground")
        webView.frame = NSRect(origin: .zero, size: screenFrame.size)
        webView.autoresizingMask = [.width, .height]
        contentView = webView
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    /// Loads the overlay page from the engine's local server.
    ///
    /// - Parameter overlayURL: The address the engine announced.
    func loadOverlay(from overlayURL: URL) {
        webView.load(URLRequest(url: overlayURL))
    }

    /// Shows the panel without taking focus from the game.
    func showOverlay() {
        orderFrontRegardless()
    }

    /// Hides the panel.
    func hideOverlay() {
        orderOut(nil)
    }

    /// Covers another frame: the screen League is on, its window, or the main screen.
    ///
    /// - Parameter screenFrame: The frame, in AppKit's coordinates.
    func cover(screenFrame: NSRect) {
        setFrame(screenFrame, display: true)
    }

    /// Lets clicks through to the game, or catches them (to move widgets, later).
    ///
    /// - Parameter isClickThrough: Whether clicks pass through.
    func setClickThrough(_ isClickThrough: Bool) {
        ignoresMouseEvents = isClickThrough
    }

    /// Puts the panel at a window level.
    ///
    /// - Parameter levelChoice: The level.
    func place(at levelChoice: WindowLevelChoice) {
        level = levelChoice.windowLevel
    }
}
