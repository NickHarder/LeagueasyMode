import AppKit
import Carbon.HIToolbox
import OverlayCore
import ServiceManagement

/// The app: a menu bar item, the overlay panel, the engine it starts and the show/hide shortcut.
/// It runs on the main thread, as AppKit does.
@MainActor
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
    // The update check: whether the player wants it (on unless turned off), and when it last asked.
    private static let checksForUpdatesKey = "checksForUpdates"
    private static let lastUpdateCheckKey = "lastUpdateCheck"
    // How often the app sees whether a check is due; the check itself is at most once a day.
    private static let updateTimerSeconds: TimeInterval = 60 * 60
    // How often the app looks for League's window, which can move, resize or change screens.
    private static let gameWindowTimerSeconds: TimeInterval = 2

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
    private var isEditingLayout = false
    private var engineStatusText = "Engine: starting…"
    private var availableRelease: AvailableRelease?
    private var updateTimer: Timer?
    private var gamePlacement: GamePlacement?
    private var gameWindowTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let placement = Self.currentGamePlacement()
        let panel = OverlayPanel(screenFrame: placement.frame)
        panel.place(at: levelChoice)
        overlayPanel = panel
        gamePlacement = placement
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
        UserDefaults.standard.register(defaults: [Self.checksForUpdatesKey: true])
        checkForUpdatesIfDue()
        updateTimer = Timer.scheduledTimer(
            timeInterval: Self.updateTimerSeconds,
            target: self,
            selector: #selector(updateTimerFired(_:)),
            userInfo: nil,
            repeats: true
        )
        gameWindowTimer = Timer.scheduledTimer(
            timeInterval: Self.gameWindowTimerSeconds,
            target: self,
            selector: #selector(gameWindowTimerFired(_:)),
            userInfo: nil,
            repeats: true
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        engineProcess?.stop()
    }

    // MARK: - The engine

    private func startEngine() {
        guard
            let command = EngineCommand.choose(
                environment: ProcessInfo.processInfo.environment,
                contentsURL: Bundle.main.bundleURL.appendingPathComponent("Contents"),
                sourceFileURL: URL(fileURLWithPath: #filePath),
                homeDirectory: FileManager.default.homeDirectoryForCurrentUser
            )
        else {
            updateEngineStatus(
                "Engine: not found (no bundled engine; set \(RepositoryLocator.overrideVariable))"
            )
            return
        }
        let process = EngineProcess(
            command: command,
            onOverlayURL: { [weak self] overlayURL in
                self?.engineDidAnnounce(overlayURL)
            },
            onExit: { [weak self] exitStatus in
                self?.updateEngineStatus("Engine: stopped (exit \(exitStatus))")
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
        // A page loaded afresh is out of edit mode; so is the app.
        isEditingLayout = false
        overlayPanel?.setEditingLayout(false, isClickThrough: isClickThrough)
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

    // MARK: - Updates and login

    /// The app's version, from its bundle; nil when it is not a bundle, as from `swift run`, which a
    /// clone updates instead.
    private static var appVersion: ReleaseVersion? {
        (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String).flatMap { ReleaseVersion($0) }
    }

    private static var isBundledApp: Bool {
        Bundle.main.bundleURL.pathExtension == "app"
    }

    private var checksForUpdates: Bool {
        UserDefaults.standard.bool(forKey: Self.checksForUpdatesKey)
    }

    /// Asks GitHub for the latest release, when the player allows it and a day has passed since the
    /// last time. A failed request waits for the next day like any other.
    private func checkForUpdatesIfDue() {
        let lastCheckedAt = UserDefaults.standard.object(forKey: Self.lastUpdateCheckKey) as? Date
        guard
            checksForUpdates,
            let appVersion = Self.appVersion,
            UpdateCheck.isDue(lastCheckedAt: lastCheckedAt, now: Date())
        else {
            return
        }
        UserDefaults.standard.set(Date(), forKey: Self.lastUpdateCheckKey)
        let request = UpdateCheck.request(appVersion: appVersion)
        // On the main actor, as this method is; the request itself waits without holding it.
        Task { [weak self] in
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                    return
                }
                self?.didFindRelease(UpdateCheck.newerRelease(answer: data, appVersion: appVersion))
            } catch {
                NSLog("LeagueasyMode: the update check did not reach GitHub: %@", error.localizedDescription)
            }
        }
    }

    private func didFindRelease(_ release: AvailableRelease?) {
        availableRelease = release
        statusItem?.menu = makeMenu()
    }

    @objc private func updateTimerFired(_ timer: Timer) {
        checkForUpdatesIfDue()
    }

    @objc private func toggleUpdateCheck(_ sender: NSMenuItem) {
        UserDefaults.standard.set(!checksForUpdates, forKey: Self.checksForUpdatesKey)
        if !checksForUpdates {
            availableRelease = nil
        }
        checkForUpdatesIfDue()
        statusItem?.menu = makeMenu()
    }

    @objc private func openReleasePage(_ sender: NSMenuItem) {
        if let availableRelease {
            NSWorkspace.shared.open(availableRelease.pageURL)
        }
    }

    private var loginItemState: LoginItemState {
        LoginItemState(status: SMAppService.mainApp.status, isBundledApp: Self.isBundledApp)
    }

    /// Asks macOS to open the app at login, or to stop. The first time, macOS may want the player
    /// to allow it in System Settings, which this then opens.
    @objc private func toggleOpenAtLogin(_ sender: NSMenuItem) {
        do {
            switch loginItemState {
            case .on, .needsApproval:
                try SMAppService.mainApp.unregister()
            case .off:
                try SMAppService.mainApp.register()
            case .unavailable:
                return
            }
        } catch {
            NSLog("LeagueasyMode: open at login did not change: %@", error.localizedDescription)
        }
        if loginItemState == .needsApproval {
            SMAppService.openSystemSettingsLoginItems()
        }
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
        if let gamePlacement {
            menu.addItem(Self.disabledItem(gamePlacement.menuText))
        }
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
        if overlayURL != nil {
            let editItem = NSMenuItem(
                title: "Edit layout", action: #selector(toggleEditLayout(_:)), keyEquivalent: ""
            )
            editItem.target = self
            editItem.state = isEditingLayout ? .on : .off
            menu.addItem(editItem)
            let resetItem = NSMenuItem(
                title: "Reset layout", action: #selector(resetLayout(_:)), keyEquivalent: ""
            )
            resetItem.target = self
            menu.addItem(resetItem)
        } else {
            menu.addItem(Self.disabledItem("Edit layout"))
        }
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
        addUpdateAndLoginItems(to: menu)
        let quitItem = NSMenuItem(
            title: "Quit LeagueasyMode", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"
        )
        menu.addItem(quitItem)
        return menu
    }

    /// The items of a bundled app: a newer release, the update check's switch and open at login.
    private func addUpdateAndLoginItems(to menu: NSMenu) {
        guard Self.isBundledApp else {
            return
        }
        if let availableRelease {
            let releaseItem = NSMenuItem(
                title: availableRelease.menuTitle, action: #selector(openReleasePage(_:)), keyEquivalent: ""
            )
            releaseItem.target = self
            menu.addItem(releaseItem)
        }
        let updateItem = NSMenuItem(
            title: "Check for updates daily", action: #selector(toggleUpdateCheck(_:)), keyEquivalent: ""
        )
        updateItem.target = self
        updateItem.state = checksForUpdates ? .on : .off
        menu.addItem(updateItem)
        let loginState = loginItemState
        if loginState != .unavailable {
            let loginItem = NSMenuItem(
                title: loginState.menuTitle, action: #selector(toggleOpenAtLogin(_:)), keyEquivalent: ""
            )
            loginItem.target = self
            loginItem.state = loginState.isChecked ? .on : .off
            menu.addItem(loginItem)
        }
        menu.addItem(.separator())
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
        // In edit mode the panel takes clicks whatever this says; it applies once editing ends.
        if !isEditingLayout {
            overlayPanel?.setClickThrough(isClickThrough)
        }
        statusItem?.menu = makeMenu()
    }

    /// Turns edit mode on or off: on, the overlay takes clicks and its widgets can be dragged.
    @objc private func toggleEditLayout(_ sender: NSMenuItem) {
        isEditingLayout.toggle()
        if isEditingLayout && !isOverlayShown {
            toggleOverlay()
        }
        overlayPanel?.setEditingLayout(isEditingLayout, isClickThrough: isClickThrough)
        statusItem?.menu = makeMenu()
    }

    @objc private func resetLayout(_ sender: NSMenuItem) {
        overlayPanel?.resetLayout()
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
        followGameWindow()
    }

    @objc private func gameWindowTimerFired(_ timer: Timer) {
        followGameWindow()
    }

    /// Moves the overlay over League's window when it has moved, resized or changed screens.
    private func followGameWindow() {
        let placement = Self.currentGamePlacement()
        guard placement != gamePlacement else {
            return
        }
        gamePlacement = placement
        overlayPanel?.cover(screenFrame: placement.frame)
        statusItem?.menu = makeMenu()
    }

    /// Where the overlay goes now: over League's game window when one is on screen, found by its
    /// owner's name and bounds, which need no permission; otherwise over the main screen.
    private static func currentGamePlacement() -> GamePlacement {
        let windowInfos =
            CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] ?? []
        let windows = windowInfos.compactMap { ListedWindow(windowInfo: $0) }
        return GameWindowLocator.placement(
            gameWindow: GameWindowLocator.gameWindow(in: windows),
            screenFrames: NSScreen.screens.map(\.frame),
            titleBarHeight: titleBarHeight
        )
    }

    /// The height of an ordinary window's title bar, which League's window has when windowed.
    private static var titleBarHeight: CGFloat {
        let contentRect = NSRect(x: 0, y: 0, width: 100, height: 100)
        return NSWindow.frameRect(forContentRect: contentRect, styleMask: [.titled]).height - contentRect.height
    }
}
