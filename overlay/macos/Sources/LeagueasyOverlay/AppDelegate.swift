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
    private static let reportShortcutDescription = "⌃⌥⌘R"
    private static let reportHotKeyIdentifier: UInt32 = 2
    // How long the app waits before starting a stopped engine again, so its port is free.
    private static let engineRestartDelaySeconds: TimeInterval = 3
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
    // Whether a newer build is installed without asking, once no game is on screen (on unless
    // turned off), and the build an install started, to say so after the restart.
    private static let installsUpdatesKey = "installsUpdatesAutomatically"
    private static let installingBuildKey = "installingBuild"
    private static let lastUpdateCheckKey = "lastUpdateCheck"
    // Whether the How to use page was opened by itself once, on the first start.
    private static let hasShownHowToUseKey = "hasShownHowToUse"
    // How often the app sees whether a check is due; the check itself is at most once a day.
    private static let updateTimerSeconds: TimeInterval = 60 * 60
    // How often the app looks for League's window, which can move, resize or change screens.
    private static let gameWindowTimerSeconds: TimeInterval = 2

    private var statusItem: NSStatusItem?
    private var overlayPanel: OverlayPanel?
    private var engineProcess: EngineProcess?
    private var toggleHotKey: GlobalHotKey?
    private var reportHotKey: GlobalHotKey?
    private var markHotKeys: [GlobalHotKey] = []
    private var markSequence = MarkSequence()
    private var overlayURL: URL?
    private var levelChoice = WindowLevelChoice.initialChoice
    private var isOverlayShown = true
    private var isEditingLayout = false
    // When edit mode was turned on; it ends by itself after `LayoutEditing.timeLimit`.
    private var editingStartedAt: Date?
    private var engineStatusText = "Engine: starting…"
    // Which build this is (`BuildInfo`), shown in the menu and handed to the engine.
    private let buildInfo = BuildInfo(infoDictionary: Bundle.main.infoDictionary)
    // This run's engine log; nil when it could not be made.
    private var engineLogURL: URL?
    private var pageState = OverlayPageState.waiting
    // How many times the overlay found itself holding the keyboard and gave it back to the game.
    private var keyboardHandBackCount = 0
    private var availableRelease: AvailableRelease?
    // A newer build CI published from main, which "Install update" puts in place.
    private var availableBuild: AvailableBuild?
    // What became of the last install, for the menu; nil before the first.
    private var updateStatusText: String?
    private var isInstallingUpdate = false
    // A build whose automatic install failed is not tried again by itself; the menu still offers it.
    private var failedBuildNumber: Int?
    private var updateTimer: Timer?
    private var gamePlacement: GamePlacement?
    private var gameWindowTimer: Timer?
    // How often a stopped engine is started again; none once the app is quitting.
    private var restartPolicy = EngineRestartPolicy()
    private var isTerminating = false
    // What became of the last problem report, for the menu; nil before the first.
    private var reportStatusText: String?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let placement = Self.currentGamePlacement()
        let panel = OverlayPanel(screenFrame: placement.frame)
        panel.place(at: levelChoice)
        panel.onEscape = { [weak self] in
            self?.endEditingLayout()
        }
        panel.onPageStateChange = { [weak self] pageState in
            self?.pageStateDidChange(pageState)
        }
        panel.onKeyboardHandedBack = { [weak self] in
            self?.keyboardWasHandedBack()
        }
        overlayPanel = panel
        gamePlacement = placement
        statusItem = makeStatusItem()
        toggleHotKey = GlobalHotKey(
            identifier: Self.toggleHotKeyIdentifier,
            keyCode: UInt32(kVK_ANSI_L),
            modifiers: UInt32(cmdKey | optionKey | controlKey)
        ) { [weak self] in
            self?.shortcutPressed()
        }
        if toggleHotKey == nil {
            NSLog("LeagueasyMode: the shortcut %@ is taken; use the menu", Self.toggleShortcutDescription)
        }
        reportHotKey = GlobalHotKey(
            identifier: Self.reportHotKeyIdentifier,
            keyCode: UInt32(kVK_ANSI_R),
            modifiers: UInt32(cmdKey | optionKey | controlKey)
        ) { [weak self] in
            self?.sendProblemReport(note: "")
        }
        if reportHotKey == nil {
            NSLog("LeagueasyMode: the shortcut %@ is taken; use the menu", Self.reportShortcutDescription)
        }
        registerMarkHotKeys()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(screensDidChange(_:)),
            name: NSApplication.didChangeScreenParametersNotification,
            object: nil
        )
        startEngine()
        UserDefaults.standard.register(defaults: [Self.checksForUpdatesKey: true, Self.installsUpdatesKey: true])
        sayWhetherAnUpdateWasInstalled()
        // At each start, whatever the last check: a fix is usually waiting when the app is opened.
        checkForUpdates(isForced: true)
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
        isTerminating = true
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
        let logDirectory = EngineLog.directory(homeDirectory: FileManager.default.homeDirectoryForCurrentUser)
        engineLogURL = try? EngineLog.startNewLog(in: logDirectory)
        let process = EngineProcess(
            command: command,
            logURL: engineLogURL,
            extraEnvironment: [
                "LEAGUEASYMODE_BUILD": buildInfo.label,
                "LEAGUEASYMODE_ENGINE_LOG": engineLogURL?.path ?? "",
            ],
            onOverlayURL: { [weak self] overlayURL in
                self?.engineDidAnnounce(overlayURL)
            },
            onExit: { [weak self] exitStatus in
                self?.engineDidStop(exitStatus: exitStatus)
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
        editingStartedAt = nil
        overlayPanel?.setEditingLayout(false)
        overlayPanel?.loadOverlay(from: overlayURL)
        if isOverlayShown {
            overlayPanel?.showOverlay()
        }
        updateEngineStatus("Engine: running")
        showHowToUseOnce(overlayURL: overlayURL)
    }

    /// Opens the How to use page the first time the engine is up, and never again by itself.
    private func showHowToUseOnce(overlayURL: URL) {
        guard
            !UserDefaults.standard.bool(forKey: Self.hasShownHowToUseKey),
            let pageURL = EnginePage.howToUse.url(overlayURL: overlayURL)
        else {
            return
        }
        UserDefaults.standard.set(true, forKey: Self.hasShownHowToUseKey)
        NSWorkspace.shared.open(pageURL)
    }

    /// Starts a stopped engine again after a moment, unless the app is quitting or the engine has
    /// stopped too often (`EngineRestartPolicy`); its log then holds why, in the previous run's file.
    private func engineDidStop(exitStatus: Int32) {
        engineProcess = nil
        overlayURL = nil
        guard !isTerminating else {
            return
        }
        guard restartPolicy.shouldRestart(at: Date()) else {
            updateEngineStatus("Engine: stopped (exit \(exitStatus)) after repeated restarts")
            return
        }
        updateEngineStatus("Engine: stopped (exit \(exitStatus)); starting again…")
        Timer.scheduledTimer(
            timeInterval: Self.engineRestartDelaySeconds,
            target: self,
            selector: #selector(engineRestartTimerFired(_:)),
            userInfo: nil,
            repeats: false
        )
    }

    @objc private func engineRestartTimerFired(_ timer: Timer) {
        if !isTerminating && engineProcess == nil {
            startEngine()
        }
    }

    private func updateEngineStatus(_ statusText: String) {
        engineStatusText = statusText
        statusItem?.menu = makeMenu()
    }

    private func pageStateDidChange(_ newPageState: OverlayPageState) {
        pageState = newPageState
        statusItem?.menu = makeMenu()
    }

    private func keyboardWasHandedBack() {
        keyboardHandBackCount += 1
        NSLog("LeagueasyMode: the overlay held the keyboard outside edit mode; handed it back")
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

    private func checkForUpdatesIfDue() {
        checkForUpdates(isForced: false)
    }

    /// Asks GitHub for the latest release and the newest build, when the player allows it and a
    /// day has passed since the last time, or at once when forced; the player asking from the menu
    /// is allowed even with the daily check off. A failed request waits for the next check.
    private func checkForUpdates(isForced: Bool, isAskedFor: Bool = false) {
        let lastCheckedAt = UserDefaults.standard.object(forKey: Self.lastUpdateCheckKey) as? Date
        guard
            checksForUpdates || isAskedFor,
            let appVersion = Self.appVersion,
            isForced || UpdateCheck.isDue(lastCheckedAt: lastCheckedAt, now: Date())
        else {
            return
        }
        checkForBuilds(appVersion: appVersion)
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

    /// Asks GitHub for the builds CI published from main, for "Install update".
    private func checkForBuilds(appVersion: ReleaseVersion) {
        let request = BuildUpdateCheck.request(appVersion: appVersion)
        let appBuildNumber = buildInfo.ciBuildNumber
        Task { [weak self] in
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                    self?.buildCheckDidFail()
                    return
                }
                self?.didFindBuild(
                    BuildUpdateCheck.newerBuild(answer: data, appVersion: appVersion, appBuildNumber: appBuildNumber)
                )
            } catch {
                NSLog("LeagueasyMode: the build check did not reach GitHub: %@", error.localizedDescription)
                self?.buildCheckDidFail()
            }
        }
    }

    private func didFindBuild(_ build: AvailableBuild?) {
        availableBuild = build
        // A line saying a build was just installed stays until the player checks again.
        let saysInstalled = updateStatusText?.hasSuffix(" installed") == true
        if !isInstallingUpdate && !(saysInstalled && build == nil) {
            let checkedAt = Date().formatted(date: .omitted, time: .shortened)
            updateStatusText = build == nil ? "Update: this is the newest build (checked \(checkedAt))" : nil
        }
        statusItem?.menu = makeMenu()
        installAutomaticallyIfPossible()
    }

    private var installsUpdatesAutomatically: Bool {
        UserDefaults.standard.bool(forKey: Self.installsUpdatesKey)
    }

    /// Installs the newer build without asking, when the player allows it and no game is on screen
    /// (`AutomaticUpdate`); otherwise it waits, and the game window's timer asks again.
    private func installAutomaticallyIfPossible() {
        guard
            let build = availableBuild,
            build.buildNumber != failedBuildNumber,
            AutomaticUpdate.canInstallNow(
                isOn: installsUpdatesAutomatically,
                placement: gamePlacement,
                isEditingLayout: isEditingLayout,
                isInstalling: isInstallingUpdate
            )
        else {
            return
        }
        startInstalling(build)
    }

    /// After a restart, says which build an install put in place, or that it did not take.
    private func sayWhetherAnUpdateWasInstalled() {
        let installingBuild = UserDefaults.standard.object(forKey: Self.installingBuildKey) as? Int
        guard let installingBuild else {
            return
        }
        UserDefaults.standard.removeObject(forKey: Self.installingBuildKey)
        updateStatusText =
            installingBuild == buildInfo.ciBuildNumber
            ? "Update: build \(installingBuild) installed"
            : "Update: build \(installingBuild) did not start; this is build \(buildInfo.ciBuildNumber.map(String.init) ?? "?")"
    }

    @objc private func toggleAutomaticInstall(_ sender: NSMenuItem) {
        UserDefaults.standard.set(!installsUpdatesAutomatically, forKey: Self.installsUpdatesKey)
        statusItem?.menu = makeMenu()
        installAutomaticallyIfPossible()
    }

    private func buildCheckDidFail() {
        if !isInstallingUpdate {
            updateStatusText = "Update: GitHub could not be asked; the next check tries again"
        }
        statusItem?.menu = makeMenu()
    }

    @objc private func checkForUpdatesNow(_ sender: NSMenuItem) {
        updateStatusText = "Update: checking…"
        checkForUpdates(isForced: true, isAskedFor: true)
        statusItem?.menu = makeMenu()
    }

    /// Asks, then downloads the newer build, puts it in place of this app, starts it and quits.
    @objc private func installUpdate(_ sender: NSMenuItem) {
        guard let build = availableBuild, !isInstallingUpdate else {
            return
        }
        let alert = NSAlert()
        alert.messageText = "Install build \(build.buildNumber)?"
        alert.informativeText =
            "LeagueasyMode downloads it, replaces itself and starts again. A game keeps running; "
            + "the overlay is back a few seconds later."
        alert.addButton(withTitle: "Install")
        alert.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else {
            return
        }
        startInstalling(build)
    }

    /// Downloads a build, puts it in place of this app, starts it and quits.
    private func startInstalling(_ build: AvailableBuild) {
        isInstallingUpdate = true
        updateStatusText = "Update: downloading build \(build.buildNumber)…"
        statusItem?.menu = makeMenu()
        // The running app, or Applications for one macOS runs from a read-only copy.
        let appURL = UpdateTarget.installURL(runningAppURL: Bundle.main.bundleURL)
        Task { [weak self] in
            do {
                try await UpdateInstaller.install(build, over: appURL)
                UserDefaults.standard.set(build.buildNumber, forKey: Self.installingBuildKey)
                try UpdateInstaller.startAgain(appURL)
                NSApp.terminate(nil)
            } catch {
                self?.updateDidFail(error, buildNumber: build.buildNumber)
            }
        }
    }

    private func updateDidFail(_ error: any Error, buildNumber: Int) {
        isInstallingUpdate = false
        failedBuildNumber = buildNumber
        updateStatusText = "Update: not installed (\(error.localizedDescription))"
        NSLog("LeagueasyMode: the update was not installed: %@", error.localizedDescription)
        statusItem?.menu = makeMenu()
    }

    private func didFindRelease(_ release: AvailableRelease?) {
        availableRelease = release
        statusItem?.menu = makeMenu()
    }

    /// Every hour: the release check when a day has passed, and the builds of main, which come
    /// with every merge.
    @objc private func updateTimerFired(_ timer: Timer) {
        if checksForUpdates, UpdateCheck.isDue(
            lastCheckedAt: UserDefaults.standard.object(forKey: Self.lastUpdateCheckKey) as? Date, now: Date()
        ) {
            checkForUpdatesIfDue()
        } else if checksForUpdates, let appVersion = Self.appVersion {
            checkForBuilds(appVersion: appVersion)
        }
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

    // MARK: - Problem reports

    /// Asks the player for an optional note, then for a report.
    @objc private func reportProblemFromMenu(_ sender: NSMenuItem) {
        let alert = NSAlert()
        alert.messageText = "Report a problem"
        alert.informativeText =
            "What went wrong? The report takes the engine's log, the status page and the game so far, "
            + "without anyone's name, and is sent with the games."
        let noteField = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 64))
        noteField.placeholderString = "Optional: what you saw"
        alert.accessoryView = noteField
        alert.addButton(withTitle: "Send report")
        alert.addButton(withTitle: "Cancel")
        NSApp.activate(ignoringOtherApps: true)
        alert.window.initialFirstResponder = noteField
        guard alert.runModal() == .alertFirstButtonReturn else {
            return
        }
        sendProblemReport(note: noteField.stringValue)
    }

    /// Asks the engine for a problem report with the app's own lines, which it then sends.
    private func sendProblemReport(note: String) {
        guard let overlayURL else {
            reportDidFinish("Report: could not be made (the engine is not running)")
            return
        }
        let request: URLRequest
        do {
            request = try ProblemReportRequest.make(overlayURL: overlayURL, note: note, appFacts: appFacts)
        } catch {
            reportDidFinish("Report: could not be made (\(error.localizedDescription))")
            return
        }
        reportDidFinish("Report: being made…")
        // On the main actor, as this method is; the request itself waits without holding it.
        Task { [weak self] in
            do {
                let (_, response) = try await URLSession.shared.data(for: request)
                let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
                if statusCode == 201 {
                    let sentAt = Date().formatted(date: .omitted, time: .shortened)
                    self?.reportDidFinish("Report: made at \(sentAt), being sent")
                } else {
                    self?.reportDidFinish("Report: could not be made (HTTP \(statusCode))")
                }
            } catch {
                self?.reportDidFinish("Report: could not be made (\(error.localizedDescription))")
            }
        }
    }

    private func reportDidFinish(_ statusText: String) {
        reportStatusText = statusText
        statusItem?.menu = makeMenu()
    }

    /// The app's own lines, which the engine cannot see, for a problem report.
    private var appFacts: [String: String] {
        var facts = [
            "build": buildInfo.label,
            "engine": engineStatusText,
            "page": pageState.menuText,
            "overlay": isOverlayShown ? "shown" : "hidden",
            "editing layout": isEditingLayout ? "yes" : "no",
            "window level": levelChoice.menuTitle,
            "macOS": ProcessInfo.processInfo.operatingSystemVersionString,
        ]
        if let gamePlacement {
            facts["game window"] = gamePlacement.menuText
        }
        if let keyboardText = KeyboardHandBack.menuText(handBackCount: keyboardHandBackCount) {
            facts["keyboard"] = keyboardText
        }
        return facts
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
        menu.addItem(Self.disabledItem("LeagueasyMode \(buildInfo.label)"))
        menu.addItem(Self.disabledItem(engineStatusText))
        menu.addItem(Self.disabledItem(pageState.menuText))
        if let keyboardText = KeyboardHandBack.menuText(handBackCount: keyboardHandBackCount) {
            menu.addItem(Self.disabledItem(keyboardText))
        }
        if let gamePlacement {
            menu.addItem(Self.disabledItem(gamePlacement.menuText))
        }
        if let reportStatusText {
            menu.addItem(Self.disabledItem(reportStatusText))
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
        if overlayURL != nil {
            let editItem = NSMenuItem(
                title: "Edit layout (Esc to finish)", action: #selector(toggleEditLayout(_:)), keyEquivalent: ""
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
        let reportTitle = "Report a problem… (\(Self.reportShortcutDescription) sends one without a note)"
        if overlayURL != nil {
            let reportItem = NSMenuItem(
                title: reportTitle, action: #selector(reportProblemFromMenu(_:)), keyEquivalent: ""
            )
            reportItem.target = self
            menu.addItem(reportItem)
        } else {
            menu.addItem(Self.disabledItem(reportTitle))
        }
        if engineLogURL != nil {
            let logItem = NSMenuItem(title: "Open engine log", action: #selector(openEngineLog(_:)), keyEquivalent: "")
            logItem.target = self
            menu.addItem(logItem)
        } else {
            menu.addItem(Self.disabledItem("Open engine log"))
        }
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
        if let updateStatusText {
            menu.addItem(Self.disabledItem(updateStatusText))
        }
        if let availableBuild, !isInstallingUpdate {
            let buildItem = NSMenuItem(
                title: availableBuild.menuTitle, action: #selector(installUpdate(_:)), keyEquivalent: ""
            )
            buildItem.target = self
            menu.addItem(buildItem)
        }
        if let availableRelease {
            let releaseItem = NSMenuItem(
                title: availableRelease.menuTitle, action: #selector(openReleasePage(_:)), keyEquivalent: ""
            )
            releaseItem.target = self
            menu.addItem(releaseItem)
        }
        let checkNowItem = NSMenuItem(
            title: "Check for updates now", action: #selector(checkForUpdatesNow(_:)), keyEquivalent: ""
        )
        checkNowItem.target = self
        menu.addItem(checkNowItem)
        let updateItem = NSMenuItem(
            title: "Check for updates", action: #selector(toggleUpdateCheck(_:)), keyEquivalent: ""
        )
        updateItem.target = self
        updateItem.state = checksForUpdates ? .on : .off
        menu.addItem(updateItem)
        let automaticItem = NSMenuItem(
            title: "Install updates automatically (not during a game)",
            action: #selector(toggleAutomaticInstall(_:)),
            keyEquivalent: ""
        )
        automaticItem.target = self
        automaticItem.state = installsUpdatesAutomatically ? .on : .off
        menu.addItem(automaticItem)
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

    /// The shortcut: ends edit mode when it is on, so that it always gives the mouse back to the
    /// game; otherwise shows or hides the overlay.
    private func shortcutPressed() {
        if isEditingLayout {
            endEditingLayout()
        } else {
            toggleOverlay()
        }
    }

    private func toggleOverlay() {
        isOverlayShown.toggle()
        if isOverlayShown {
            overlayPanel?.showOverlay()
        } else {
            // A hidden overlay takes no clicks, and edit mode ends with it.
            if isEditingLayout {
                endEditingLayout()
            }
            overlayPanel?.hideOverlay()
        }
        statusItem?.menu = makeMenu()
    }

    @objc private func toggleOverlayFromMenu(_ sender: NSMenuItem) {
        toggleOverlay()
    }

    /// Turns edit mode on or off: on, the overlay is tinted, takes clicks and its widgets can be
    /// dragged, until Escape, the shortcut, the menu or the time limit ends it.
    @objc private func toggleEditLayout(_ sender: NSMenuItem) {
        if isEditingLayout {
            endEditingLayout()
            return
        }
        if !isOverlayShown {
            toggleOverlay()
        }
        isEditingLayout = true
        editingStartedAt = Date()
        overlayPanel?.setEditingLayout(true)
        statusItem?.menu = makeMenu()
    }

    /// Ends edit mode: the overlay lets every click through to the game again.
    private func endEditingLayout() {
        isEditingLayout = false
        editingStartedAt = nil
        overlayPanel?.setEditingLayout(false)
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

    /// Opens this run's engine log in the app macOS opens logs with (Console).
    @objc private func openEngineLog(_ sender: NSMenuItem) {
        guard let engineLogURL else {
            return
        }
        NSWorkspace.shared.open(engineLogURL)
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
        installAutomaticallyIfPossible()
        if let editingStartedAt, LayoutEditing.hasRunOut(startedAt: editingStartedAt, now: Date()) {
            endEditingLayout()
        }
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
