import AppKit
import OverlayCore
import WebKit

/// A transparent window over League, its screen or its window, that shows the overlay page.
///
/// It never becomes main and its panel does not activate the app, so League keeps the keyboard
/// and the focus; clicks pass through it to the game. Only in edit mode does it become key and
/// take clicks, so its widgets can be dragged. It joins every Space, the full-screen ones included.
final class OverlayPanel: NSPanel {
    private let webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
    private var isEditingLayout = false

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
        // The page hands its callouts to the app's voice, when the player turned speech on.
        webView.configuration.userContentController.add(SpeechBridge(), name: SpokenCallout.messageName)
        contentView = webView
    }

    override var canBecomeKey: Bool { isEditingLayout }
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

    /// Turns edit mode on or off: the panel takes clicks and the page lets its widgets be dragged,
    /// or the panel goes back to letting clicks through as the menu says.
    ///
    /// - Parameters:
    ///   - isEditing: Whether edit mode is on.
    ///   - isClickThrough: Whether clicks pass through outside edit mode.
    func setEditingLayout(_ isEditing: Bool, isClickThrough: Bool) {
        isEditingLayout = isEditing
        ignoresMouseEvents = isEditing ? false : isClickThrough
        webView.evaluateJavaScript(LayoutEditing.editingScript(isEditing: isEditing))
        if isEditing {
            // A non-activating panel becomes key without bringing the app forward.
            makeKeyAndOrderFront(nil)
        }
    }

    /// Puts every widget back in its usual place.
    func resetLayout() {
        webView.evaluateJavaScript(LayoutEditing.resetScript)
    }

    /// Puts the panel at a window level.
    ///
    /// - Parameter levelChoice: The level.
    func place(at levelChoice: WindowLevelChoice) {
        level = levelChoice.windowLevel
    }
}
