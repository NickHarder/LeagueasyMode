import AppKit
import Carbon.HIToolbox
import OverlayCore

/// The app: a menu bar item, the overlay panel, the engine it starts and the show/hide shortcut.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private static let toggleShortcutDescription = "⌃⌥⌘L"

    private var statusItem: NSStatusItem?
    private var overlayPanel: OverlayPanel?
    private var engineProcess: EngineProcess?
    private var toggleHotKey: GlobalHotKey?
    private var levelChoice = WindowLevelChoice.initialChoice
    private var isOverlayShown = true
    private var isClickThrough = true
    private var engineStatusText = "Engine: starting…"

    func applicationDidFinishLaunching(_ notification: Notification) {
        let panel = OverlayPanel(screenFrame: Self.gameScreenFrame())
        panel.place(at: levelChoice)
        overlayPanel = panel
        statusItem = makeStatusItem()
        toggleHotKey = GlobalHotKey(
            keyCode: UInt32(kVK_ANSI_L), modifiers: UInt32(cmdKey | optionKey | controlKey)
        ) { [weak self] in
            self?.toggleOverlay()
        }
        if toggleHotKey == nil {
            NSLog("LeagueasyMode: the shortcut %@ is taken; use the menu", Self.toggleShortcutDescription)
        }
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(screensDidChange(_:)),
            name: NSApplication.didChangeScreenParametersNotification,
            object: nil
        )
        startEngine()
    }

    func applicationWillTerminate(_ notification: Notification) {
        engineProcess?.stop()
    }

    // MARK: - The engine

    private func startEngine() {
        let environment = ProcessInfo.processInfo.environment
        guard
            let repositoryRoot = RepositoryLocator.repositoryRoot(
                sourceFileURL: URL(fileURLWithPath: #filePath), environment: environment
            )
        else {
            updateEngineStatus(
                "Engine: repository not found (set \(RepositoryLocator.overrideVariable))"
            )
            return
        }
        let command = EngineCommand.make(
            repositoryRoot: repositoryRoot,
            inheritedEnvironment: environment,
            homeDirectory: FileManager.default.homeDirectoryForCurrentUser
        )
        let process = EngineProcess(
            command: command,
            onOverlayURL: { [weak self] overlayURL in
                DispatchQueue.main.async { self?.engineDidAnnounce(overlayURL) }
            },
            onExit: { [weak self] exitStatus in
                DispatchQueue.main.async { self?.updateEngineStatus("Engine: stopped (exit \(exitStatus))") }
            }
        )
        do {
            try process.start()
            engineProcess = process
        } catch {
            updateEngineStatus("Engine: could not start uv (\(error.localizedDescription))")
        }
    }

    private func engineDidAnnounce(_ overlayURL: URL) {
        overlayPanel?.loadOverlay(from: overlayURL)
        if isOverlayShown {
            overlayPanel?.showOverlay()
        }
        updateEngineStatus("Engine: running")
    }

    private func updateEngineStatus(_ statusText: String) {
        engineStatusText = statusText
        statusItem?.menu = makeMenu()
    }

    // MARK: - The menu

    private func makeStatusItem() -> NSStatusItem {
        let newStatusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        newStatusItem.button?.image = NSImage(
            systemSymbolName: "scope", accessibilityDescription: "LeagueasyMode"
        )
        newStatusItem.menu = makeMenu()
        return newStatusItem
    }

    private func makeMenu() -> NSMenu {
        let menu = NSMenu()
        menu.addItem(Self.disabledItem("LeagueasyMode"))
        menu.addItem(Self.disabledItem(engineStatusText))
        menu.addItem(.separator())
        let showItem = NSMenuItem(
            title: "Show overlay (\(Self.toggleShortcutDescription))",
            action: #selector(toggleOverlayFromMenu(_:)),
            keyEquivalent: ""
        )
        showItem.target = self
        showItem.state = isOverlayShown ? .on : .off
        menu.addItem(showItem)
        let clickThroughItem = NSMenuItem(
            title: "Let clicks through", action: #selector(toggleClickThrough(_:)), keyEquivalent: ""
        )
        clickThroughItem.target = self
        clickThroughItem.state = isClickThrough ? .on : .off
        menu.addItem(clickThroughItem)
        let levelItem = NSMenuItem(title: "Window level", action: nil, keyEquivalent: "")
        levelItem.submenu = makeLevelMenu()
        menu.addItem(levelItem)
        menu.addItem(.separator())
        let quitItem = NSMenuItem(
            title: "Quit LeagueasyMode", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"
        )
        menu.addItem(quitItem)
        return menu
    }

    private func makeLevelMenu() -> NSMenu {
        let levelMenu = NSMenu()
        for choice in WindowLevelChoice.allCases {
            let choiceItem = NSMenuItem(
                title: choice.menuTitle, action: #selector(chooseLevel(_:)), keyEquivalent: ""
            )
            choiceItem.target = self
            choiceItem.representedObject = choice.rawValue
            choiceItem.state = choice == levelChoice ? .on : .off
            levelMenu.addItem(choiceItem)
        }
        return levelMenu
    }

    private static func disabledItem(_ title: String) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        item.isEnabled = false
        return item
    }

    // MARK: - Actions

    private func toggleOverlay() {
        isOverlayShown.toggle()
        if isOverlayShown {
            overlayPanel?.showOverlay()
        } else {
            overlayPanel?.hideOverlay()
        }
        statusItem?.menu = makeMenu()
    }

    @objc private func toggleOverlayFromMenu(_ sender: NSMenuItem) {
        toggleOverlay()
    }

    @objc private func toggleClickThrough(_ sender: NSMenuItem) {
        isClickThrough.toggle()
        overlayPanel?.setClickThrough(isClickThrough)
        statusItem?.menu = makeMenu()
    }

    @objc private func chooseLevel(_ sender: NSMenuItem) {
        guard
            let rawValue = sender.representedObject as? String,
            let choice = WindowLevelChoice(rawValue: rawValue)
        else {
            return
        }
        levelChoice = choice
        overlayPanel?.place(at: choice)
        statusItem?.menu = makeMenu()
    }

    @objc private func screensDidChange(_ notification: Notification) {
        overlayPanel?.cover(screenFrame: Self.gameScreenFrame())
    }

    /// The frame of the screen the game is on: the main screen, where full-screen games open.
    private static func gameScreenFrame() -> NSRect {
        (NSScreen.main ?? NSScreen.screens.first)?.frame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
    }
}
