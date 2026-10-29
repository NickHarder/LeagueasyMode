import AppKit
import OverlayCore
import WebKit

/// A transparent window over League, its screen or its window, that shows the overlay page.
///
/// It never becomes main and its panel does not activate the app, so League keeps the keyboard
/// and the focus; clicks pass through it to the game. Only in edit mode does it become key and
/// take clicks, so its widgets can be dragged: then it is tinted, so that the player sees the
/// layer that catches their clicks even when the page shows nothing, and Escape ends it. With
/// "Click to mark spells" on, it also takes the clicks on the page's spell buttons, and those
/// alone, while the pointer is over one (`ClickRegions`); it still never becomes key then. The page
/// shows its buttons only while Tab or Option is held (`DetailsKey`), so at a glance the panel
/// takes no click at all. It joins every Space, the full-screen ones included.
final class OverlayPanel: NSPanel, WKNavigationDelegate {
    // How often the panel looks where the pointer is, to take a click on a spell button: 30 times
    // a second, so that the button is ready before a click lands on it.
    private static let pointerCheckSeconds: TimeInterval = 1.0 / 30
    private let webView = OverlayWebView(frame: .zero, configuration: WKWebViewConfiguration())
    private var isEditingLayout = false
    // The page's spell buttons, in its points from its top left; none unless the setting is on.
    private var clickRegions: [CGRect] = []
    private var pointerTimer: Timer?
    // Looks whether Tab or Option is held, and tells the page when that changes.
    private var detailsKeyTimer: Timer?
    private var detailsKeyWatcher = DetailsKeyWatcher()
    // When the panel last gave the keyboard back; at most once a second, so that a panel AppKit
    // made key again on showing could never hide and show itself without end.
    private var lastKeyboardHandBack: Date?
    /// Called when the player presses Escape in edit mode.
    var onEscape: (@MainActor () -> Void)?
    /// Called when the page starts loading, has loaded, or did not load.
    var onPageStateChange: (@MainActor (OverlayPageState) -> Void)?
    /// Called when the panel found itself holding the keyboard outside edit mode and gave it back.
    var onKeyboardHandedBack: (@MainActor () -> Void)?

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
        // The page says where its spell buttons are, so that the panel takes those clicks only.
        webView.configuration.userContentController.add(
            ClickRegionBridge { [weak self] rectangles in
                self?.clickRegionsDidChange(rectangles)
            },
            name: ClickRegions.messageName
        )
        webView.navigationDelegate = self
        contentView = webView
        detailsKeyTimer = Timer.scheduledTimer(
            timeInterval: DetailsKey.checkSeconds,
            target: self,
            selector: #selector(detailsKeyTimerFired(_:)),
            userInfo: nil,
            repeats: true
        )
    }

    /// Tells the page whether Tab or Option is held, when that changes. It reads only whether the
    /// keys are down; the keys still go to the game.
    @objc private func detailsKeyTimerFired(_ timer: Timer) {
        let isOptionDown = NSEvent.modifierFlags.contains(.option)
        let isTabDown = CGEventSource.keyState(.combinedSessionState, key: DetailsKey.tabKeyCode)
        if let script = detailsKeyWatcher.scriptForChange(isOptionDown: isOptionDown, isTabDown: isTabDown) {
            webView.evaluateJavaScript(script)
        }
    }

    override var canBecomeKey: Bool { isEditingLayout }

    /// Keeps the page's spell buttons, and looks for the pointer only while there are some.
    private func clickRegionsDidChange(_ rectangles: [CGRect]) {
        clickRegions = rectangles
        if rectangles.isEmpty {
            pointerTimer?.invalidate()
            pointerTimer = nil
            if !isEditingLayout {
                ignoresMouseEvents = true
            }
        } else if pointerTimer == nil {
            pointerTimer = Timer.scheduledTimer(
                timeInterval: Self.pointerCheckSeconds,
                target: self,
                selector: #selector(pointerTimerFired(_:)),
                userInfo: nil,
                repeats: true
            )
        }
    }

    /// Takes the mouse while the pointer is over a spell button, and lets it through elsewhere.
    @objc private func pointerTimerFired(_ timer: Timer) {
        guard !isEditingLayout else {
            return
        }
        let pointer = NSEvent.mouseLocation
        let pointInWindow = CGPoint(x: pointer.x - frame.minX, y: pointer.y - frame.minY)
        let isOverButton =
            isVisible
            && ClickRegions.contains(clickRegions, pointInWindow: pointInWindow, windowHeight: frame.height)
        if ignoresMouseEvents == isOverButton {
            ignoresMouseEvents = !isOverButton
        }
    }
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
        // Out of edit mode the pointer check gives the spell buttons their clicks again.
        ignoresMouseEvents = !isEditing
        backgroundColor = isEditing ? NSColor.black.withAlphaComponent(0.3) : .clear
        webView.evaluateJavaScript(LayoutEditing.editingScript(isEditing: isEditing))
        if isEditing {
            // A non-activating panel becomes key without bringing the app forward.
            makeKeyAndOrderFront(nil)
        } else if isKeyWindow {
            releaseKeyboard()
        }
    }

    /// Outside edit mode the keyboard is the game's. On the first try on a Mac the panel held it
    /// without edit mode, by a path not yet known, and hiding and showing it gave it back; so it
    /// does that itself, once AppKit has finished making it key.
    override func becomeKey() {
        super.becomeKey()
        if !isEditingLayout {
            perform(#selector(handKeyboardBack), with: nil, afterDelay: 0)
        }
    }

    @objc private func handKeyboardBack() {
        let now = Date()
        guard
            isKeyWindow,
            !isEditingLayout,
            lastKeyboardHandBack.map({ now.timeIntervalSince($0) >= 1 }) ?? true
        else {
            return
        }
        lastKeyboardHandBack = now
        releaseKeyboard()
        onKeyboardHandedBack?()
    }

    /// Hides the panel and shows it again, which leaves the keyboard to the window below it.
    private func releaseKeyboard() {
        let wasVisible = isVisible
        orderOut(nil)
        if wasVisible {
            orderFrontRegardless()
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

    /// Puts the panel at a window level, or higher when the game's window needs it.
    ///
    /// - Parameters:
    ///   - levelChoice: The level chosen in the menu.
    ///   - lowestLevel: The level that clears League's window, when League raised it.
    func place(at levelChoice: WindowLevelChoice, atLeast lowestLevel: Int? = nil) {
        level = NSWindow.Level(rawValue: max(levelChoice.windowLevel.rawValue, lowestLevel ?? Int.min))
    }

    // MARK: - Whether the page loaded

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        onPageStateChange?(.loading)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // A page loaded again does not know whether the key is held; the next check tells it.
        detailsKeyWatcher.forget()
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

/// The page's view. A click on a spell button lands on a panel that is not key, so the view takes
/// that first click rather than spending it on making the panel key, which it never becomes.
final class OverlayWebView: WKWebView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }
}

/// Hands the page's spell buttons, as `ClickRegions` reads them, to the panel.
final class ClickRegionBridge: NSObject, WKScriptMessageHandler {
    private let onRectangles: @MainActor ([CGRect]) -> Void

    init(onRectangles: @escaping @MainActor ([CGRect]) -> Void) {
        self.onRectangles = onRectangles
    }

    func userContentController(
        _ userContentController: WKUserContentController, didReceive message: WKScriptMessage
    ) {
        guard let rectangles = ClickRegions.rectangles(fromMessageBody: message.body) else {
            return
        }
        // WebKit hands the page's messages over on the main thread.
        MainActor.assumeIsolated {
            onRectangles(rectangles)
        }
    }
}
