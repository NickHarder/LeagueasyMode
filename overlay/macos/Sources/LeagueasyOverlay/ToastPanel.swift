import AppKit

/// A short note near the top of the game's screen, such as "Copied: …", gone after a few seconds.
///
/// It never takes the mouse or the keyboard, which League keeps: the panel is borderless and does
/// not activate the app, so it cannot become the key window, and it lets every click through.
@MainActor
final class ToastPanel {
    private static let shownSeconds: Double = 2.5
    private static let height: CGFloat = 36
    private static let topMargin: CGFloat = 56
    private static let sidePadding: CGFloat = 16
    private static let narrowest: CGFloat = 160

    private let panel: NSPanel
    private let label: NSTextField
    // Counts the toasts shown, so that a newer toast is not hidden by an older one's timer.
    private var shownCount = 0

    init() {
        label = NSTextField(labelWithString: "")
        label.font = NSFont.systemFont(ofSize: 14, weight: .medium)
        label.textColor = .white
        label.lineBreakMode = .byTruncatingTail
        label.translatesAutoresizingMaskIntoConstraints = false
        let background = NSView()
        background.wantsLayer = true
        background.layer?.backgroundColor = NSColor(white: 0.08, alpha: 0.9).cgColor
        background.layer?.cornerRadius = 10
        background.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: background.leadingAnchor, constant: Self.sidePadding),
            label.trailingAnchor.constraint(equalTo: background.trailingAnchor, constant: -Self.sidePadding),
            label.centerYAnchor.constraint(equalTo: background.centerYAnchor),
        ])
        panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: Self.narrowest, height: Self.height),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: true
        )
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.ignoresMouseEvents = true
        panel.hidesOnDeactivate = false
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.contentView = background
    }

    /// Shows a note centered near the top of a screen area, and hides it a few seconds later.
    ///
    /// - Parameters:
    ///   - text: The note.
    ///   - screenFrame: Where League's window is, or the screen, in AppKit's coordinates.
    func show(_ text: String, over screenFrame: CGRect) {
        label.stringValue = text
        let widest = max(Self.narrowest, screenFrame.width - 2 * Self.sidePadding)
        let width = min(widest, max(Self.narrowest, label.intrinsicContentSize.width + 2 * Self.sidePadding))
        let origin = CGPoint(
            x: screenFrame.midX - width / 2,
            y: screenFrame.maxY - Self.topMargin - Self.height
        )
        panel.setFrame(NSRect(origin: origin, size: CGSize(width: width, height: Self.height)), display: true)
        panel.orderFrontRegardless()
        shownCount += 1
        let thisToast = shownCount
        let shownNanoseconds = UInt64(Self.shownSeconds * 1_000_000_000)
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: shownNanoseconds)
            self?.hide(ifStill: thisToast)
        }
    }

    private func hide(ifStill toast: Int) {
        guard toast == shownCount else {
            return
        }
        panel.orderOut(nil)
    }
}
