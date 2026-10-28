import AppKit
import OverlayCore
import WebKit

/// A transparent window over League, its screen or its window, that shows the overlay page.
///
/// It never becomes main and its panel does not activate the app, so League keeps the keyboard
/// and the focus; clicks always pass through it to the game. Only in edit mode does it become key
/// and take clicks, so its widgets can be dragged: then it is tinted, so that the player sees the
/// layer that catches their clicks even when the page shows nothing, and Escape ends it. It joins
/// every Space, the full-screen ones included.
final class OverlayPanel: NSPanel, WKNavigationDelegate {
    private let webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
    private var isEditingLayout = false
    /// Called when the player presses Escape in edit mode.
    var onEscape: (@MainActor () -> Void)?
    /// Called when the page starts loading, has loaded, or did not load.
    var onPageStateChange: (@MainActor (OverlayPageState) -> Void)?

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
        webView.navigationDelegate = self
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

    /// Turns edit mode on or off: the panel is tinted, takes clicks and the page lets its widgets
    /// be dragged; or the panel is clear again and lets every click through to the game.
    ///
    /// - Parameter isEditing: Whether edit mode is on.
    func setEditingLayout(_ isEditing: Bool) {
        isEditingLayout = isEditing
        ignoresMouseEvents = !isEditing
        backgroundColor = isEditing ? NSColor.black.withAlphaComponent(0.3) : .clear
        webView.evaluateJavaScript(LayoutEditing.editingScript(isEditing: isEditing))
        if isEditing {
            // A non-activating panel becomes key without bringing the app forward.
            makeKeyAndOrderFront(nil)
        }
    }

    /// Ends edit mode on Escape, before the page sees the key.
    override func sendEvent(_ event: NSEvent) {
        if isEditingLayout, event.type == .keyDown, LayoutEditing.endsEditing(keyCode: event.keyCode) {
            onEscape?()
            return
        }
        super.sendEvent(event)
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

    // MARK: - Whether the page loaded

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        onPageStateChange?(.loading)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        onPageStateChange?(.loaded)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
        onPageStateChange?(.failed(error.localizedDescription))
    }

    func webView(
        _ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: any Error
    ) {
        onPageStateChange?(.failed(error.localizedDescription))
    }

    /// The page's own process stopped, which leaves the overlay blank: load the page again.
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        onPageStateChange?(.failed("its process stopped; loading it again"))
        webView.reload()
    }
}
