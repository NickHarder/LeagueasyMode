import AppKit
import Carbon.HIToolbox
import OverlayCore

/// The app: a menu bar item, the overlay panel, the engine it starts and the show/hide shortcut.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private static let toggleShortcutDescription = "⌃⌥⌘L"
    private static let toggleHotKeyIdentifier: UInt32 = 1
    // ⌃⌥1 to ⌃⌥5 pick an enemy in role order; ⌃⌥F, ⌃⌥D and ⌃⌥R name the spell they used.
    private static let firstPickHotKeyIdentifier: UInt32 = 10
    private static let firstSpellHotKeyIdentifier: UInt32 = 20
    private static let markModifiers = UInt32(controlKey | optionKey)
    private static let pickKeys: [(keyCode: UInt32, enemySlot: Int)] = [
        (UInt32(kVK_ANSI_1), 1),
        (UInt32(kVK_ANSI_2), 2),
        (UInt32(kVK_ANSI_3), 3),
        (UInt32(kVK_ANSI_4), 4),
        (UInt32(kVK_ANSI_5), 5),
    ]
    private static let spellKeys: [(keyCode: UInt32, spell: MarkedSpell)] = [
        (UInt32(kVK_ANSI_F), .flash),
        (UInt32(kVK_ANSI_D), .summoner),
        (UInt32(kVK_ANSI_R), .ultimate),
    ]

    private var statusItem: NSStatusItem?
    private var overlayPanel: OverlayPanel?
    private var engineProcess: EngineProcess?
    private var toggleHotKey: GlobalHotKey?
    private var markHotKeys: [GlobalHotKey] = []
    private var markSequence = MarkSequence()
    private var overlayURL: URL?
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
            identifier: Self.toggleHotKeyIdentifier,
            keyCode: UInt32(kVK_ANSI_L),
            modifiers: UInt32(cmdKey | optionKey | controlKey)
        ) { [weak self] in
            self?.toggleOverlay()
        }
        if toggleHotKey == nil {
            NSLog("LeagueasyMode: the shortcut %@ is taken; use the menu", Self.toggleShortcutDescription)
        }
        registerMarkHotKeys()
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
        self.overlayURL = overlayURL
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

    // MARK: - Marking cooldowns

    private func registerMarkHotKeys() {
        let pickHotKeys = Self.pickKeys.enumerated().compactMap { offset, pickKey in
            GlobalHotKey(
                identifier: Self.firstPickHotKeyIdentifier + UInt32(offset),
                keyCode: pickKey.keyCode,
                modifiers: Self.markModifiers
            ) { [weak self] in
                self?.pickEnemy(slot: pickKey.enemySlot)
            }
        }
        let spellHotKeys = Self.spellKeys.enumerated().compactMap { offset, spellKey in
            GlobalHotKey(
                identifier: Self.firstSpellHotKeyIdentifier + UInt32(offset),
                keyCode: spellKey.keyCode,
                modifiers: Self.markModifiers
            ) { [weak self] in
                self?.markSpell(spellKey.spell)
            }
        }
        markHotKeys = pickHotKeys + spellHotKeys
        if markHotKeys.count < Self.pickKeys.count + Self.spellKeys.count {
            NSLog("LeagueasyMode: some ⌃⌥ marking shortcuts are taken by another app")
        }
    }

    private func pickEnemy(slot: Int) {
        markSequence.pickEnemy(slot: slot, atSeconds: ProcessInfo.processInfo.systemUptime)
    }

    private func markSpell(_ spell: MarkedSpell) {
        guard
            let mark = markSequence.markSpell(spell, atSeconds: ProcessInfo.processInfo.systemUptime),
            let overlayURL
        else {
            return
        }
        let request = MarkRequest.make(overlayURL: overlayURL, mark: mark)
        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error {
                NSLog("LeagueasyMode: the mark did not reach the engine: %@", error.localizedDescription)
            } else if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                NSLog("LeagueasyMode: the engine did not take the mark (HTTP %ld)", httpResponse.statusCode)
            }
        }.resume()
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
        for page in EnginePage.allCases {
            if overlayURL != nil {
                let pageItem = NSMenuItem(
                    title: page.menuTitle, action: #selector(openEnginePage(_:)), keyEquivalent: ""
                )
                pageItem.target = self
                pageItem.representedObject = page.rawValue
                menu.addItem(pageItem)
            } else {
                menu.addItem(Self.disabledItem(page.menuTitle))
            }
        }
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

    /// Opens one of the engine's pages in the default browser: a normal window, unlike the overlay.
    @objc private func openEnginePage(_ sender: NSMenuItem) {
        guard
            let rawValue = sender.representedObject as? String,
            let page = EnginePage(rawValue: rawValue),
            let overlayURL,
            let pageURL = page.url(overlayURL: overlayURL)
        else {
            return
        }
        NSWorkspace.shared.open(pageURL)
    }

    @objc private func screensDidChange(_ notification: Notification) {
        overlayPanel?.cover(screenFrame: Self.gameScreenFrame())
    }

    /// The frame of the screen the game is on: the main screen, where full-screen games open.
    private static func gameScreenFrame() -> NSRect {
        (NSScreen.main ?? NSScreen.screens.first)?.frame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
    }
}
