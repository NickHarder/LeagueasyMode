import CoreGraphics
import Foundation
import ServiceManagement
import XCTest

@testable import OverlayCore

final class EngineAnnouncementTests: XCTestCase {
    func testTheEnginesLineGivesTheOverlayAddress() {
        let overlayURL = EngineAnnouncement.overlayURL(
            fromLine: "LEAGUEASYMODE_OVERLAY_URL=http://127.0.0.1:52011/\n"
        )
        XCTAssertEqual(overlayURL, URL(string: "http://127.0.0.1:52011/"))
    }

    func testAnyOtherLineIsIgnored() {
        XCTAssertNil(EngineAnnouncement.overlayURL(fromLine: "2026-10-08 INFO waiting for a game"))
    }

    func testAnAddressThatIsNotLocalIsRefused() {
        XCTAssertNil(
            EngineAnnouncement.overlayURL(fromLine: "LEAGUEASYMODE_OVERLAY_URL=http://example.com:80/")
        )
        XCTAssertNil(
            EngineAnnouncement.overlayURL(fromLine: "LEAGUEASYMODE_OVERLAY_URL=https://127.0.0.1:443/")
        )
        XCTAssertNil(EngineAnnouncement.overlayURL(fromLine: "LEAGUEASYMODE_OVERLAY_URL=http://127.0.0.1/"))
    }
}

final class LineBufferTests: XCTestCase {
    func testLinesArriveWholeWhateverTheChunks() {
        var lineBuffer = LineBuffer()
        XCTAssertEqual(lineBuffer.append(Data("first li".utf8)), [])
        XCTAssertEqual(lineBuffer.append(Data("ne\nsecond line\nthi".utf8)), ["first line", "second line"])
        XCTAssertEqual(lineBuffer.append(Data("rd\n".utf8)), ["third"])
    }
}

final class EngineCommandTests: XCTestCase {
    func testTheEngineRunsThroughUvFromTheRepository() {
        let command = EngineCommand.make(
            repositoryRoot: URL(fileURLWithPath: "/Users/player/LeagueasyMode"),
            inheritedEnvironment: ["PATH": "/usr/bin:/bin", "HOME": "/Users/player"],
            homeDirectory: URL(fileURLWithPath: "/Users/player")
        )
        XCTAssertEqual(command.executableURL.path, "/usr/bin/env")
        XCTAssertEqual(
            command.arguments,
            ["uv", "run", "--project", "/Users/player/LeagueasyMode", "leagueasymode", "run"]
        )
        XCTAssertEqual(command.environment["HOME"], "/Users/player")
    }

    func testUvsUsualPlacesFollowThePathTheAppHas() {
        let command = EngineCommand.make(
            repositoryRoot: URL(fileURLWithPath: "/repository"),
            inheritedEnvironment: ["PATH": "/usr/bin:/opt/homebrew/bin"],
            homeDirectory: URL(fileURLWithPath: "/Users/player")
        )
        XCTAssertEqual(
            command.environment["PATH"],
            "/usr/bin:/opt/homebrew/bin:/Users/player/.local/bin:/Users/player/.cargo/bin:/usr/local/bin"
        )
    }

    func testTheBundledEngineRunsThroughTheBundledUv() {
        let bundledEngine = BundledEngine(
            uvURL: URL(fileURLWithPath: "/Applications/LeagueasyMode.app/Contents/Helpers/uv"),
            wheelURL: URL(fileURLWithPath: "/Resources/engine/leagueasymode-0.1.0-py3-none-any.whl"),
            constraintsURL: URL(fileURLWithPath: "/Resources/engine/constraints.txt"),
            pythonVersion: "3.12"
        )
        let command = EngineCommand.make(
            bundledEngine: bundledEngine, inheritedEnvironment: ["HOME": "/Users/player"]
        )
        XCTAssertEqual(
            command.executableURL.path, "/Applications/LeagueasyMode.app/Contents/Helpers/uv"
        )
        XCTAssertEqual(
            command.arguments,
            [
                "tool", "run", "--from", "/Resources/engine/leagueasymode-0.1.0-py3-none-any.whl",
                "--constraints", "/Resources/engine/constraints.txt", "--python", "3.12",
                "leagueasymode", "run",
            ]
        )
        XCTAssertEqual(command.environment, ["HOME": "/Users/player"])
    }

    func testWithoutAPythonVersionUvChoosesOne() {
        let bundledEngine = BundledEngine(
            uvURL: URL(fileURLWithPath: "/Helpers/uv"),
            wheelURL: URL(fileURLWithPath: "/Resources/engine/engine.whl"),
            constraintsURL: URL(fileURLWithPath: "/Resources/engine/constraints.txt"),
            pythonVersion: nil
        )
        let command = EngineCommand.make(bundledEngine: bundledEngine, inheritedEnvironment: [:])
        XCTAssertFalse(command.arguments.contains("--python"))
    }
}

final class BundledEngineTests: XCTestCase {
    private var temporaryDirectory: URL!
    private var contentsDirectory: URL!
    private var engineDirectory: URL!

    override func setUpWithError() throws {
        temporaryDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        contentsDirectory = temporaryDirectory.appendingPathComponent(
            "LeagueasyMode.app/Contents", isDirectory: true
        )
        engineDirectory = contentsDirectory.appendingPathComponent("Resources/engine", isDirectory: true)
        let helpersDirectory = contentsDirectory.appendingPathComponent("Helpers", isDirectory: true)
        try FileManager.default.createDirectory(at: engineDirectory, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: helpersDirectory, withIntermediateDirectories: true)
        let uvPath = helpersDirectory.appendingPathComponent("uv").path
        XCTAssertTrue(FileManager.default.createFile(atPath: uvPath, contents: Data()))
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: uvPath)
        for fileName in [
            "leagueasymode-0.1.0-py3-none-any.whl", "leagueasymode-0.2.0-py3-none-any.whl",
            "constraints.txt",
        ] {
            try Data().write(to: engineDirectory.appendingPathComponent(fileName))
        }
        try Data("3.12\n".utf8).write(to: engineDirectory.appendingPathComponent("python-version"))
    }

    override func tearDownWithError() throws {
        try FileManager.default.removeItem(at: temporaryDirectory)
    }

    func testTheBundleHoldsTheEngine() throws {
        let bundledEngine = try XCTUnwrap(BundledEngine.locate(contentsURL: contentsDirectory))
        XCTAssertEqual(bundledEngine.uvURL.lastPathComponent, "uv")
        XCTAssertEqual(bundledEngine.wheelURL.lastPathComponent, "leagueasymode-0.2.0-py3-none-any.whl")
        XCTAssertEqual(bundledEngine.constraintsURL.lastPathComponent, "constraints.txt")
        XCTAssertEqual(bundledEngine.pythonVersion, "3.12")
    }

    func testWithoutAPythonVersionFileThereIsNoVersion() throws {
        try FileManager.default.removeItem(at: engineDirectory.appendingPathComponent("python-version"))
        let bundledEngine = try XCTUnwrap(BundledEngine.locate(contentsURL: contentsDirectory))
        XCTAssertNil(bundledEngine.pythonVersion)
    }

    func testAUvThatCannotRunIsNoEngine() throws {
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o644],
            ofItemAtPath: contentsDirectory.appendingPathComponent("Helpers/uv").path
        )
        XCTAssertNil(BundledEngine.locate(contentsURL: contentsDirectory))
    }

    func testNoWheelIsNoEngine() throws {
        for fileName in ["leagueasymode-0.1.0-py3-none-any.whl", "leagueasymode-0.2.0-py3-none-any.whl"] {
            try FileManager.default.removeItem(at: engineDirectory.appendingPathComponent(fileName))
        }
        XCTAssertNil(BundledEngine.locate(contentsURL: contentsDirectory))
    }

    func testNoConstraintsIsNoEngine() throws {
        try FileManager.default.removeItem(at: engineDirectory.appendingPathComponent("constraints.txt"))
        XCTAssertNil(BundledEngine.locate(contentsURL: contentsDirectory))
    }

    func testABuildThatIsNoBundleIsNoEngine() {
        XCTAssertNil(
            BundledEngine.locate(contentsURL: URL(fileURLWithPath: "/nowhere/.build/debug/Contents"))
        )
    }

    func testTheAppRunsTheEngineItCarries() throws {
        let command = try XCTUnwrap(
            EngineCommand.choose(
                environment: [:],
                contentsURL: contentsDirectory,
                sourceFileURL: URL(fileURLWithPath: "/nowhere/AppDelegate.swift"),
                homeDirectory: URL(fileURLWithPath: "/Users/player")
            )
        )
        XCTAssertEqual(command.executableURL.lastPathComponent, "uv")
        XCTAssertEqual(Array(command.arguments.prefix(2)), ["tool", "run"])
    }

    func testTheRepositoryVariablePrefersTheClone() throws {
        let command = try XCTUnwrap(
            EngineCommand.choose(
                environment: [RepositoryLocator.overrideVariable: "/Users/player/LeagueasyMode"],
                contentsURL: contentsDirectory,
                sourceFileURL: URL(fileURLWithPath: "/nowhere/AppDelegate.swift"),
                homeDirectory: URL(fileURLWithPath: "/Users/player")
            )
        )
        XCTAssertEqual(command.executableURL.path, "/usr/bin/env")
        XCTAssertEqual(
            Array(command.arguments.prefix(4)), ["uv", "run", "--project", "/Users/player/LeagueasyMode"]
        )
    }

    func testWithNeitherThereIsNoEngine() {
        XCTAssertNil(
            EngineCommand.choose(
                environment: [:],
                contentsURL: URL(fileURLWithPath: "/nowhere/.build/debug/Contents"),
                sourceFileURL: URL(fileURLWithPath: "/nowhere/AppDelegate.swift"),
                homeDirectory: URL(fileURLWithPath: "/Users/player")
            )
        )
    }
}

final class RepositoryLocatorTests: XCTestCase {
    private var temporaryDirectory: URL!

    override func setUpWithError() throws {
        temporaryDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let sourceDirectory = temporaryDirectory.appendingPathComponent(
            "overlay/macos/Sources/LeagueasyOverlay", isDirectory: true
        )
        try FileManager.default.createDirectory(at: sourceDirectory, withIntermediateDirectories: true)
        try Data().write(to: temporaryDirectory.appendingPathComponent("pyproject.toml"))
    }

    override func tearDownWithError() throws {
        try FileManager.default.removeItem(at: temporaryDirectory)
    }

    func testTheRepositoryIsFoundAboveTheSourceFile() {
        let sourceFile = temporaryDirectory.appendingPathComponent(
            "overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift"
        )
        let repositoryRoot = RepositoryLocator.repositoryRoot(sourceFileURL: sourceFile, environment: [:])
        XCTAssertEqual(repositoryRoot?.standardizedFileURL.path, temporaryDirectory.standardizedFileURL.path)
    }

    func testTheVariableOverridesTheSearch() {
        let repositoryRoot = RepositoryLocator.repositoryRoot(
            sourceFileURL: URL(fileURLWithPath: "/nowhere/AppDelegate.swift"),
            environment: ["LEAGUEASYMODE_REPOSITORY": "/Users/player/LeagueasyMode"]
        )
        XCTAssertEqual(repositoryRoot?.path, "/Users/player/LeagueasyMode")
    }

    func testNoRepositoryIsNil() {
        XCTAssertNil(
            RepositoryLocator.repositoryRoot(
                sourceFileURL: URL(fileURLWithPath: "/nowhere/AppDelegate.swift"), environment: [:]
            )
        )
    }
}

final class MarkSequenceTests: XCTestCase {
    func testAPickThenASpellMakesAMark() {
        var sequence = MarkSequence()
        sequence.pickEnemy(slot: 3, atSeconds: 100)
        XCTAssertEqual(
            sequence.markSpell(.flash, atSeconds: 101), CooldownMark(enemySlot: 3, spell: .flash)
        )
    }

    func testASpellWithNoPickMarksNothing() {
        var sequence = MarkSequence()
        XCTAssertNil(sequence.markSpell(.ultimate, atSeconds: 5))
    }

    func testAPickWaitsOnlyAFewSeconds() {
        var sequence = MarkSequence()
        sequence.pickEnemy(slot: 2, atSeconds: 100)
        XCTAssertNil(sequence.markSpell(.summoner, atSeconds: 100 + MarkSequence.pickWaitSeconds + 1))
    }

    func testOnePickMakesOneMark() {
        var sequence = MarkSequence()
        sequence.pickEnemy(slot: 1, atSeconds: 10)
        XCTAssertNotNil(sequence.markSpell(.flash, atSeconds: 11))
        XCTAssertNil(sequence.markSpell(.ultimate, atSeconds: 11.5))
    }

    func testALaterPickReplacesAnEarlierOne() {
        var sequence = MarkSequence()
        sequence.pickEnemy(slot: 1, atSeconds: 10)
        sequence.pickEnemy(slot: 4, atSeconds: 10.5)
        XCTAssertEqual(
            sequence.markSpell(.ultimate, atSeconds: 11), CooldownMark(enemySlot: 4, spell: .ultimate)
        )
    }

    func testAPlaceOutsideOneToFiveIsNoPick() {
        var sequence = MarkSequence()
        sequence.pickEnemy(slot: 2, atSeconds: 10)
        sequence.pickEnemy(slot: 7, atSeconds: 10.5)
        XCTAssertNil(sequence.markSpell(.flash, atSeconds: 11))
    }
}

final class MarkRequestTests: XCTestCase {
    func testAMarkIsPostedBesideTheOverlayPageWithTheAppsHeader() throws {
        let overlayURL = try XCTUnwrap(URL(string: "http://127.0.0.1:52011/"))
        let request = MarkRequest.make(
            overlayURL: overlayURL, mark: CooldownMark(enemySlot: 2, spell: .ultimate)
        )
        XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:52011/marks")
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-LeagueasyMode-Request"), "mark")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        let body = try XCTUnwrap(request.httpBody)
        let decoded = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(decoded["enemy_slot"] as? Int, 2)
        XCTAssertEqual(decoded["spell"] as? String, "ultimate")
    }
}

final class EnginePageTests: XCTestCase {
    func testEachPageIsBesideTheOverlayPage() {
        let overlayURL = URL(string: "http://127.0.0.1:52011/")!
        XCTAssertEqual(
            EnginePage.lastGame.url(overlayURL: overlayURL),
            URL(string: "http://127.0.0.1:52011/summary.html")
        )
        XCTAssertEqual(
            EnginePage.settings.url(overlayURL: overlayURL),
            URL(string: "http://127.0.0.1:52011/settings.html")
        )
        XCTAssertEqual(
            EnginePage.status.url(overlayURL: overlayURL),
            URL(string: "http://127.0.0.1:52011/status.html")
        )
        XCTAssertEqual(
            EnginePage.howToUse.url(overlayURL: overlayURL),
            URL(string: "http://127.0.0.1:52011/how-to-use.html")
        )
    }

    func testEachPageHasItsMenuTitle() {
        XCTAssertEqual(
            EnginePage.allCases.map(\.menuTitle),
            ["How to use\u{2026}", "Last game\u{2026}", "Settings\u{2026}", "Status\u{2026}"]
        )
    }
}

final class ReleaseVersionTests: XCTestCase {
    func testATagReadsAsItsNumbers() throws {
        let version = try XCTUnwrap(ReleaseVersion("v1.4.2"))
        XCTAssertEqual(version.numbers, [1, 4, 2])
        XCTAssertEqual(version.description, "1.4.2")
    }

    func testMissingNumbersAreNoughts() {
        XCTAssertEqual(ReleaseVersion("2"), ReleaseVersion("2.0.0"))
        XCTAssertEqual(ReleaseVersion("v0.3"), ReleaseVersion("0.3.0"))
    }

    func testVersionsCompareNumberByNumber() throws {
        let older = try XCTUnwrap(ReleaseVersion("0.9.12"))
        let newer = try XCTUnwrap(ReleaseVersion("0.10.0"))
        XCTAssertLessThan(older, newer)
        XCTAssertFalse(newer < older)
    }

    func testAnythingButNumbersIsNoVersion() {
        for text in ["", "v", "1.2.3.4", "1..2", "1.2-beta", "v1.2.3 ", "latest", "١.٢.٣"] {
            XCTAssertNil(ReleaseVersion(text), text)
        }
    }
}

final class UpdateCheckTests: XCTestCase {
    private let appVersion = ReleaseVersion("0.1.0")!

    /// A release's answer, with the zipped app attached as a release of the app always has it.
    private func answer(_ fields: [String: Any]) throws -> Data {
        let appFile: [String: Any] = ["name": "LeagueasyMode-0.2.0.zip"]
        let withApp = fields.merging(["assets": [appFile, ["name": "LeagueasyMode-0.2.0.zip.sha256"]]]) { given, _ in given }
        return try JSONSerialization.data(withJSONObject: withApp)
    }

    func testTheRequestAsksGitHubForTheLatestRelease() {
        let request = UpdateCheck.request(appVersion: appVersion)
        XCTAssertEqual(
            request.url?.absoluteString,
            "https://api.github.com/repos/NickHarder/LeagueasyMode/releases/latest"
        )
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/vnd.github+json")
        XCTAssertEqual(request.value(forHTTPHeaderField: "User-Agent"), "LeagueasyMode/0.1.0")
    }

    func testANewerReleaseIsOffered() throws {
        let release = try XCTUnwrap(
            UpdateCheck.newerRelease(
                answer: try answer([
                    "tag_name": "v0.2.0", "draft": false, "prerelease": false,
                    "html_url": "https://github.com/NickHarder/LeagueasyMode/releases/tag/v0.2.0",
                ]),
                appVersion: appVersion
            )
        )
        XCTAssertEqual(release.version, ReleaseVersion("0.2.0"))
        XCTAssertEqual(
            release.pageURL.absoluteString, "https://github.com/NickHarder/LeagueasyMode/releases/tag/v0.2.0"
        )
        XCTAssertEqual(release.menuTitle, "LeagueasyMode 0.2.0 is out\u{2026}")
    }

    func testTheSameOrAnOlderReleaseIsNotOffered() throws {
        for tagName in ["v0.1.0", "v0.0.9", "0.1"] {
            XCTAssertNil(
                UpdateCheck.newerRelease(answer: try answer(["tag_name": tagName]), appVersion: appVersion),
                tagName
            )
        }
    }

    func testADraftOrPrereleaseIsNotOffered() throws {
        for fields: [String: Any] in [
            ["tag_name": "v0.2.0", "draft": true],
            ["tag_name": "v0.2.0", "prerelease": true],
        ] {
            XCTAssertNil(UpdateCheck.newerRelease(answer: try answer(fields), appVersion: appVersion))
        }
    }

    func testAReleaseWithoutTheAppIsNotOffered() throws {
        // The repository's old v1.0.0 has no files: offering it led to an empty page.
        for assets: [[String: Any]] in [[], [["name": "notes.txt"]], [["name": "LeagueasyMode-1.0.0.zip.sha256"]]] {
            XCTAssertNil(
                UpdateCheck.newerRelease(answer: try answer(["tag_name": "v1.0.0", "assets": assets]), appVersion: appVersion),
                "\(assets)"
            )
        }
        let noAssetsField = try JSONSerialization.data(withJSONObject: ["tag_name": "v1.0.0"])
        XCTAssertNil(UpdateCheck.newerRelease(answer: noAssetsField, appVersion: appVersion))
    }

    func testThePageIsAlwaysThisRepositorysWhateverTheAnswerSays() throws {
        let release = try XCTUnwrap(
            UpdateCheck.newerRelease(
                answer: try answer(["tag_name": "v0.2.0", "html_url": "https://example.com/download"]),
                appVersion: appVersion
            )
        )
        XCTAssertEqual(release.pageURL.host, "github.com")
        XCTAssertEqual(release.pageURL.path, "/NickHarder/LeagueasyMode/releases/tag/v0.2.0")
    }

    func testAnAnswerThatIsNoReleaseIsIgnored() throws {
        XCTAssertNil(UpdateCheck.newerRelease(answer: Data("not json".utf8), appVersion: appVersion))
        XCTAssertNil(
            UpdateCheck.newerRelease(answer: try answer(["message": "Not Found"]), appVersion: appVersion)
        )
        XCTAssertNil(
            UpdateCheck.newerRelease(answer: try answer(["tag_name": "nightly"]), appVersion: appVersion)
        )
    }

    func testTheCheckIsDueOnceADay() {
        let lastCheck = Date(timeIntervalSince1970: 1_000_000)
        XCTAssertTrue(UpdateCheck.isDue(lastCheckedAt: nil, now: lastCheck))
        XCTAssertFalse(UpdateCheck.isDue(lastCheckedAt: lastCheck, now: lastCheck.addingTimeInterval(23 * 3600)))
        XCTAssertTrue(UpdateCheck.isDue(lastCheckedAt: lastCheck, now: lastCheck.addingTimeInterval(24 * 3600)))
    }

    func testAClockSetBackDoesNotStopTheChecks() {
        let lastCheck = Date(timeIntervalSince1970: 1_000_000)
        XCTAssertTrue(UpdateCheck.isDue(lastCheckedAt: lastCheck, now: lastCheck.addingTimeInterval(-60)))
    }
}

final class LoginItemStateTests: XCTestCase {
    func testTheSystemsAnswerIsTheMenuItemsState() {
        XCTAssertEqual(LoginItemState(status: .enabled, isBundledApp: true), .on)
        XCTAssertEqual(LoginItemState(status: .notRegistered, isBundledApp: true), .off)
        XCTAssertEqual(LoginItemState(status: .notFound, isBundledApp: true), .off)
        XCTAssertEqual(LoginItemState(status: .requiresApproval, isBundledApp: true), .needsApproval)
    }

    func testAnAppRunFromTheTerminalCannotOpenAtLogin() {
        XCTAssertEqual(LoginItemState(status: .enabled, isBundledApp: false), .unavailable)
    }

    func testEachStateHasItsMenuItem() {
        XCTAssertEqual(LoginItemState.on.menuTitle, "Open at login")
        XCTAssertTrue(LoginItemState.on.isChecked)
        XCTAssertFalse(LoginItemState.off.isChecked)
        XCTAssertEqual(LoginItemState.needsApproval.menuTitle, "Open at login (allow in System Settings\u{2026})")
        XCTAssertTrue(LoginItemState.needsApproval.isChecked)
    }
}

final class GameWindowLocatorTests: XCTestCase {
    // A 1920 × 1080 main screen, and a 2560 × 1440 one to its right, bottoms level.
    private let mainScreen = CGRect(x: 0, y: 0, width: 1920, height: 1080)
    private let secondScreen = CGRect(x: 1920, y: 0, width: 2560, height: 1440)
    private let titleBarHeight: CGFloat = 28

    private func leagueWindow(_ bounds: CGRect, ownerName: String = "League of Legends") -> ListedWindow {
        ListedWindow(ownerName: ownerName, bounds: bounds, layer: 0)
    }

    func testLeaguesGameWindowIsFoundByItsOwnersName() {
        let windows = [
            ListedWindow(ownerName: "LeagueClientUx", bounds: CGRect(x: 0, y: 0, width: 1280, height: 720), layer: 0),
            leagueWindow(CGRect(x: 0, y: 0, width: 1920, height: 1080), ownerName: "LeagueofLegends"),
            ListedWindow(ownerName: "Finder", bounds: CGRect(x: 0, y: 0, width: 3000, height: 3000), layer: 0),
        ]
        XCTAssertEqual(GameWindowLocator.gameWindow(in: windows)?.ownerName, "LeagueofLegends")
    }

    func testAWindowAboveTheGamesLayerIsNotTheGame() {
        let windows = [
            ListedWindow(ownerName: "League of Legends", bounds: CGRect(x: 0, y: 0, width: 40, height: 40), layer: 25)
        ]
        XCTAssertNil(GameWindowLocator.gameWindow(in: windows))
    }

    func testOfSeveralWindowsTheLargestIsTheGame() {
        let windows = [
            leagueWindow(CGRect(x: 0, y: 0, width: 300, height: 200)),
            leagueWindow(CGRect(x: 0, y: 0, width: 1920, height: 1080)),
        ]
        XCTAssertEqual(GameWindowLocator.gameWindow(in: windows)?.bounds.width, 1920)
    }

    func testAFullScreenGameIsCoveredScreenAndAll() {
        let placement = GameWindowLocator.placement(
            gameWindow: leagueWindow(CGRect(x: 0, y: 0, width: 1920, height: 1080)),
            screenFrames: [mainScreen, secondScreen],
            titleBarHeight: titleBarHeight
        )
        XCTAssertEqual(placement, .screen(mainScreen))
        XCTAssertEqual(placement.frame, mainScreen)
    }

    func testAGameOnTheSecondScreenIsCoveredThere() {
        // The window server counts down from the main screen's top: the second screen's top is
        // 360 points above it.
        let placement = GameWindowLocator.placement(
            gameWindow: leagueWindow(CGRect(x: 1920, y: -360, width: 2560, height: 1440)),
            screenFrames: [mainScreen, secondScreen],
            titleBarHeight: titleBarHeight
        )
        XCTAssertEqual(placement, .screen(secondScreen))
    }

    func testAWindowedGameIsCoveredBelowItsTitleBar() {
        let placement = GameWindowLocator.placement(
            gameWindow: leagueWindow(CGRect(x: 100, y: 100, width: 1280, height: 748)),
            screenFrames: [mainScreen, secondScreen],
            titleBarHeight: titleBarHeight
        )
        XCTAssertEqual(placement, .window(CGRect(x: 100, y: 232, width: 1280, height: 720)))
    }

    func testWithNoGameWindowTheMainScreenIsCovered() {
        let placement = GameWindowLocator.placement(
            gameWindow: nil, screenFrames: [mainScreen, secondScreen], titleBarHeight: titleBarHeight
        )
        XCTAssertEqual(placement, .mainScreen(mainScreen))
    }

    func testEachPlacementSaysWhatWasFound() {
        XCTAssertEqual(GamePlacement.screen(mainScreen).menuText, "League: full screen, 1920 × 1080")
        XCTAssertEqual(
            GamePlacement.window(CGRect(x: 100, y: 232, width: 1280, height: 720)).menuText,
            "League: windowed, 1280 × 720"
        )
        XCTAssertEqual(GamePlacement.mainScreen(mainScreen).menuText, "League: no game window seen")
    }

    func testAWindowServerEntryIsRead() throws {
        let entry: [String: Any] = [
            kCGWindowOwnerName as String: "League of Legends",
            kCGWindowLayer as String: 0,
            kCGWindowBounds as String: ["X": 10, "Y": 20, "Width": 1280, "Height": 748] as NSDictionary,
        ]
        let window = try XCTUnwrap(ListedWindow(windowInfo: entry))
        XCTAssertEqual(window, leagueWindow(CGRect(x: 10, y: 20, width: 1280, height: 748)))
        XCTAssertNil(ListedWindow(windowInfo: [kCGWindowOwnerName as String: "League of Legends"]))
    }
}

final class LayoutEditingTests: XCTestCase {
    func testEditModeIsTurnedOnAndOffInThePage() {
        XCTAssertEqual(LayoutEditing.editingScript(isEditing: true), "window.leagueasymodeSetEditing?.(true);")
        XCTAssertEqual(LayoutEditing.editingScript(isEditing: false), "window.leagueasymodeSetEditing?.(false);")
    }

    func testResetPutsTheWidgetsBackInThePage() {
        XCTAssertEqual(LayoutEditing.resetScript, "window.leagueasymodeResetLayout?.();")
    }

    func testEditModeEndsByItselfAfterTwoMinutes() {
        let startedAt = Date(timeIntervalSince1970: 1_000)
        XCTAssertFalse(LayoutEditing.hasRunOut(startedAt: startedAt, now: startedAt.addingTimeInterval(119)))
        XCTAssertTrue(LayoutEditing.hasRunOut(startedAt: startedAt, now: startedAt.addingTimeInterval(120)))
    }

    func testEscapeEndsEditMode() {
        // 53 is the Escape key's code on every Mac keyboard layout.
        XCTAssertTrue(LayoutEditing.endsEditing(keyCode: 53))
        XCTAssertFalse(LayoutEditing.endsEditing(keyCode: 0))
    }
}

final class DetailsKeyTests: XCTestCase {
    func testTabOrOptionShowsTheDetails() {
        XCTAssertTrue(DetailsKey.isHeld(isOptionDown: false, isTabDown: true))
        XCTAssertTrue(DetailsKey.isHeld(isOptionDown: true, isTabDown: false))
        XCTAssertFalse(DetailsKey.isHeld(isOptionDown: false, isTabDown: false))
        // 48 is the Tab key's code on every Mac keyboard layout.
        XCTAssertEqual(DetailsKey.tabKeyCode, 48)
    }

    func testThePageIsToldOnlyWhenTheKeyChanges() {
        var watcher = DetailsKeyWatcher()
        XCTAssertEqual(
            watcher.scriptForChange(isOptionDown: false, isTabDown: false),
            "window.leagueasymodeSetDetailsHeld?.(false);"
        )
        XCTAssertNil(watcher.scriptForChange(isOptionDown: false, isTabDown: false))
        XCTAssertEqual(
            watcher.scriptForChange(isOptionDown: false, isTabDown: true),
            "window.leagueasymodeSetDetailsHeld?.(true);"
        )
        XCTAssertNil(watcher.scriptForChange(isOptionDown: true, isTabDown: true))
        // A page loaded again knows nothing, so it is told again.
        watcher.forget()
        XCTAssertEqual(
            watcher.scriptForChange(isOptionDown: true, isTabDown: false),
            "window.leagueasymodeSetDetailsHeld?.(true);"
        )
    }
}

final class KeyboardHandBackTests: XCTestCase {
    func testTheMenuSaysHowOftenTheKeyboardWasHandedBack() {
        XCTAssertNil(KeyboardHandBack.menuText(handBackCount: 0))
        XCTAssertEqual(KeyboardHandBack.menuText(handBackCount: 1), "Keyboard: handed back to the game once")
        XCTAssertEqual(KeyboardHandBack.menuText(handBackCount: 3), "Keyboard: handed back to the game 3 times")
    }
}

final class OverlayPageStateTests: XCTestCase {
    func testTheMenuSaysWhetherTheOverlayPageLoaded() {
        XCTAssertEqual(OverlayPageState.waiting.menuText, "Overlay: waiting for the engine")
        XCTAssertEqual(OverlayPageState.loading.menuText, "Overlay: loading the page\u{2026}")
        XCTAssertEqual(OverlayPageState.loaded.menuText, "Overlay: page loaded")
        XCTAssertEqual(
            OverlayPageState.failed("Could not connect to the server.").menuText,
            "Overlay: the page did not load (Could not connect to the server.)"
        )
    }
}

final class SpokenCalloutTests: XCTestCase {
    func testACalloutIsSpokenAsTheTextThePageSent() {
        XCTAssertEqual(SpokenCallout.text(fromMessageBody: "  Zed is level 6\n"), "Zed is level 6")
    }

    func testAnythingButAShortLineOfTextIsNotSpoken() {
        XCTAssertNil(SpokenCallout.text(fromMessageBody: 6))
        XCTAssertNil(SpokenCallout.text(fromMessageBody: "   "))
        XCTAssertNil(SpokenCallout.text(fromMessageBody: String(repeating: "a", count: 201)))
    }

    func testThePageAndTheAppAgreeOnTheMessagesName() {
        XCTAssertEqual(SpokenCallout.messageName, "leagueasymodeSpeak")
    }
}

final class BuildInfoTests: XCTestCase {
    func testABuildNamesItsVersionRunAndCommit() {
        let info = BuildInfo(infoDictionary: [
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "62",
            "LeagueasyModeCommit": "b0d63a8",
        ])
        XCTAssertEqual(info.label, "0.1.0 (build 62, b0d63a8)")
        XCTAssertEqual(info.ciBuildNumber, 62)
    }

    func testAnAppRunFromItsSourceSaysSo() {
        XCTAssertEqual(BuildInfo(infoDictionary: nil).label, "from source")
        XCTAssertEqual(BuildInfo(infoDictionary: ["CFBundleShortVersionString": "0.1.0"]).label, "0.1.0")
        let unnumbered = BuildInfo(infoDictionary: ["CFBundleShortVersionString": "0.1.0", "CFBundleVersion": "0.1.0"])
        XCTAssertNil(unnumbered.ciBuildNumber)
    }
}

final class BuildUpdateCheckTests: XCTestCase {
    private let appVersion = ReleaseVersion("0.1.0")!

    private func build(_ number: Int, version: String = "0.1.0", prerelease: Bool = true) -> [String: Any] {
        let archive = "LeagueasyMode-\(version)-build-\(number).zip"
        return [
            "tag_name": "build-\(number)", "draft": false, "prerelease": prerelease,
            "assets": [
                ["name": archive, "browser_download_url": "https://example.com/\(archive)"],
                ["name": archive + ".sha256"],
            ],
        ]
    }

    private func answer(_ releases: [[String: Any]]) throws -> Data {
        try JSONSerialization.data(withJSONObject: releases)
    }

    func testTheRequestAsksForTheNewestReleases() {
        XCTAssertEqual(
            BuildUpdateCheck.request(appVersion: appVersion).url?.absoluteString,
            "https://api.github.com/repos/NickHarder/LeagueasyMode/releases?per_page=30"
        )
    }

    func testTheNewestLaterBuildIsOfferedFromThisRepository() throws {
        let offered = try XCTUnwrap(
            BuildUpdateCheck.newerBuild(
                answer: try answer([build(70), build(75), build(62), ["tag_name": "v0.1.0", "assets": []]]),
                appVersion: appVersion,
                appBuildNumber: 62
            )
        )
        XCTAssertEqual(offered.buildNumber, 75)
        XCTAssertEqual(offered.version, ReleaseVersion("0.1.0"))
        XCTAssertEqual(
            offered.archiveURL.absoluteString,
            "https://github.com/NickHarder/LeagueasyMode/releases/download/build-75/LeagueasyMode-0.1.0-build-75.zip"
        )
        XCTAssertEqual(offered.checksumURL.lastPathComponent, "LeagueasyMode-0.1.0-build-75.zip.sha256")
        XCTAssertEqual(offered.menuTitle, "Install update: build 75 (0.1.0)\u{2026}")
    }

    func testNoBuildIsOfferedThatIsNotNewer() throws {
        XCTAssertNil(
            BuildUpdateCheck.newerBuild(answer: try answer([build(62), build(50)]), appVersion: appVersion, appBuildNumber: 62)
        )
        // A build of an older version, as after the owner's full release, is not offered either.
        XCTAssertNil(
            BuildUpdateCheck.newerBuild(
                answer: try answer([build(90)]), appVersion: ReleaseVersion("0.2.0")!, appBuildNumber: 3
            )
        )
    }

    func testOnlyAPrereleaseWithItsZipAndChecksumIsABuild() throws {
        var withoutChecksum = build(80)
        withoutChecksum["assets"] = [["name": "LeagueasyMode-0.1.0-build-80.zip"]]
        XCTAssertNil(
            BuildUpdateCheck.newerBuild(
                answer: try answer([build(81, prerelease: false), withoutChecksum, ["tag_name": "build-x", "assets": []]]),
                appVersion: appVersion,
                appBuildNumber: 62
            )
        )
        XCTAssertNil(BuildUpdateCheck.newerBuild(answer: Data("{}".utf8), appVersion: appVersion, appBuildNumber: 62))
    }

    func testAnUnnumberedAppIsOfferedAnyBuild() throws {
        let offered = BuildUpdateCheck.newerBuild(answer: try answer([build(5)]), appVersion: appVersion, appBuildNumber: nil)
        XCTAssertEqual(offered?.buildNumber, 5)
    }
}

final class AutomaticUpdateTests: XCTestCase {
    private let screen = CGRect(x: 0, y: 0, width: 1920, height: 1080)

    func testABuildIsInstalledOnlyWithNoGameOnScreen() {
        XCTAssertTrue(
            AutomaticUpdate.canInstallNow(
                isOn: true, placement: .mainScreen(screen), isEditingLayout: false, isInstalling: false
            )
        )
        for placement in [GamePlacement.screen(screen), .window(screen)] {
            XCTAssertFalse(
                AutomaticUpdate.canInstallNow(isOn: true, placement: placement, isEditingLayout: false, isInstalling: false)
            )
        }
        XCTAssertFalse(AutomaticUpdate.canInstallNow(isOn: true, placement: nil, isEditingLayout: false, isInstalling: false))
    }

    func testNotWhenOffEditingOrAlreadyInstalling() {
        let noGame = GamePlacement.mainScreen(screen)
        XCTAssertFalse(AutomaticUpdate.canInstallNow(isOn: false, placement: noGame, isEditingLayout: false, isInstalling: false))
        XCTAssertFalse(AutomaticUpdate.canInstallNow(isOn: true, placement: noGame, isEditingLayout: true, isInstalling: false))
        XCTAssertFalse(AutomaticUpdate.canInstallNow(isOn: true, placement: noGame, isEditingLayout: false, isInstalling: true))
    }
}

final class ArchiveChecksumTests: XCTestCase {
    func testTheDigestIsTheOneForTheArchive() {
        let digest = String(repeating: "ab", count: 32)
        XCTAssertEqual(
            ArchiveChecksum.expectedDigest(
                checksumFile: "\(digest)  LeagueasyMode-0.1.0-build-75.zip\n", archiveName: "LeagueasyMode-0.1.0-build-75.zip"
            ),
            digest
        )
        XCTAssertNil(ArchiveChecksum.expectedDigest(checksumFile: "\(digest)  other.zip\n", archiveName: "a.zip"))
        XCTAssertNil(ArchiveChecksum.expectedDigest(checksumFile: "short  a.zip\n", archiveName: "a.zip"))
    }

    func testTheDigestOfBytesIsSHA256() {
        XCTAssertEqual(
            ArchiveChecksum.sha256Hex(of: Data("abc".utf8)),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
    }
}

final class EngineLogTests: XCTestCase {
    func testEachStartKeepsTheLastThreeRunsLogs() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        for run in 1...4 {
            let logURL = try EngineLog.startNewLog(in: directory)
            try Data("run \(run)\n".utf8).write(to: logURL)
        }
        let names = try FileManager.default.contentsOfDirectory(atPath: directory.path).sorted()
        XCTAssertEqual(names, ["engine.1.log", "engine.2.log", "engine.log"])
        let newest = try String(contentsOf: directory.appendingPathComponent("engine.log"), encoding: .utf8)
        let oldest = try String(contentsOf: directory.appendingPathComponent("engine.2.log"), encoding: .utf8)
        XCTAssertEqual(newest, "run 4\n")
        XCTAssertEqual(oldest, "run 2\n")
    }

    func testTheLogIsKeptWhereMacOSKeepsLogs() {
        let home = URL(fileURLWithPath: "/Users/someone", isDirectory: true)
        XCTAssertEqual(EngineLog.directory(homeDirectory: home).path, "/Users/someone/Library/Logs/LeagueasyMode")
    }
}

final class ProblemReportRequestTests: XCTestCase {
    func testAReportCarriesTheNoteAndTheAppsLinesWithTheAppsHeader() throws {
        let overlayURL = try XCTUnwrap(URL(string: "http://127.0.0.1:52011/"))
        let request = try ProblemReportRequest.make(
            overlayURL: overlayURL,
            note: "keys \"stopped\"",
            appFacts: ["engine": "Engine: running", "keyboard": "Keyboard: handed back once"]
        )
        XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:52011/report")
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-LeagueasyMode-Request"), "report")
        let body = try XCTUnwrap(request.httpBody)
        let decoded = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(decoded["note"] as? String, "keys \"stopped\"")
        XCTAssertEqual((decoded["app"] as? [String: String])?["keyboard"], "Keyboard: handed back once")
    }
}

final class EngineRestartPolicyTests: XCTestCase {
    func testAStoppedEngineIsStartedAgainAtMostFiveTimesInTenMinutes() {
        var policy = EngineRestartPolicy()
        let start = Date(timeIntervalSince1970: 1_000)
        for minute in 0..<5 {
            XCTAssertTrue(policy.shouldRestart(at: start.addingTimeInterval(Double(minute) * 60)))
        }
        XCTAssertFalse(policy.shouldRestart(at: start.addingTimeInterval(5 * 60)))
        // Ten minutes after the first, there is room again.
        XCTAssertTrue(policy.shouldRestart(at: start.addingTimeInterval(10 * 60 + 1)))
    }
}

final class RoastCopyTests: XCTestCase {
    func testAFirstPressCopiesTheShownTakeAndQuickPressesTheTakesAfterIt() {
        var presses = CopyPresses()
        XCTAssertEqual(presses.press(atSeconds: 100), 0)
        XCTAssertEqual(presses.press(atSeconds: 102), 1)
        // Within five seconds of the press before, not of the first.
        XCTAssertEqual(presses.press(atSeconds: 106.5), 2)
        XCTAssertEqual(presses.press(atSeconds: 111.5), 3)
    }

    func testAPressAfterAPauseCopiesTheShownTakeAgain() {
        var presses = CopyPresses()
        XCTAssertEqual(presses.press(atSeconds: 100), 0)
        XCTAssertEqual(presses.press(atSeconds: 103), 1)
        XCTAssertEqual(presses.press(atSeconds: 108.5), 0)
        // A clock that went back starts over too.
        XCTAssertEqual(presses.press(atSeconds: 50), 0)
    }

    func testTheRequestAsksForTheTakesAfterTheShownOne() throws {
        let overlayURL = try XCTUnwrap(URL(string: "http://127.0.0.1:52011/"))
        let request = ClosingLineRequest.make(overlayURL: overlayURL, laterTakes: 2)
        XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:52011/closing-line?next=2")
        XCTAssertEqual(request.httpMethod, "GET")
    }

    func testAfterAGameTheEnginesLineIsCopied() throws {
        let body = try XCTUnwrap(#"{"text": "gg. TEAM DIFF. Our Vi died 9 times.", "take": 1}"#.data(using: .utf8))
        let line = CopyOutcome.line(statusCode: 200, body: body)
        XCTAssertEqual(line, CopiedLine(text: "gg. TEAM DIFF. Our Vi died 9 times.", take: 1))
        XCTAssertEqual(
            line.map(CopyOutcome.toastText(copied:)),
            "Copied: gg. TEAM DIFF. Our Vi died 9 times."
        )
    }

    func testDuringAGameOrWithoutACaseNothingIsCopied() throws {
        let refusal = try XCTUnwrap(#"{"message": "nothing to copy during a game yet"}"#.data(using: .utf8))
        XCTAssertNil(CopyOutcome.line(statusCode: 409, body: refusal))
        XCTAssertEqual(CopyOutcome.toastText(failedWith: 409), "Nothing to copy during a game yet")
        XCTAssertNil(CopyOutcome.line(statusCode: 404, body: refusal))
        XCTAssertEqual(
            CopyOutcome.toastText(failedWith: 404), "Nothing to copy: no case for the last game yet"
        )
        let empty = try XCTUnwrap(#"{"text": "", "take": 0}"#.data(using: .utf8))
        XCTAssertNil(CopyOutcome.line(statusCode: 200, body: empty))
        XCTAssertNil(CopyOutcome.line(statusCode: 200, body: Data("not json".utf8)))
    }

    func testTheToastCutsALongLineShort() {
        let longLine = CopiedLine(text: String(repeating: "a", count: 120), take: 0)
        let toast = CopyOutcome.toastText(copied: longLine)
        XCTAssertEqual(toast, "Copied: " + String(repeating: "a", count: 59) + "…")
    }
}

final class ClickRegionsTests: XCTestCase {
    func testThePagesButtonsAreRead() throws {
        let rectangles = try XCTUnwrap(ClickRegions.rectangles(fromMessageBody: "[[937,427,40,17],[981,427,36,17]]"))
        XCTAssertEqual(rectangles, [CGRect(x: 937, y: 427, width: 40, height: 17), CGRect(x: 981, y: 427, width: 36, height: 17)])
        XCTAssertEqual(ClickRegions.rectangles(fromMessageBody: "[]"), [])
    }

    func testAnythingElseIsRefused() {
        for body: Any in [5, "not json", "[[1,2,3]]", "[[1,2,0,4]]", "{\"left\":1}"] {
            XCTAssertNil(ClickRegions.rectangles(fromMessageBody: body), "\(body)")
        }
        let tooMany = "[" + Array(repeating: "[1,1,1,1]", count: 65).joined(separator: ",") + "]"
        XCTAssertNil(ClickRegions.rectangles(fromMessageBody: tooMany))
    }

    func testThePointerIsOverAButtonOnlyInsideIt() {
        // The page counts from its top left, AppKit from the window's bottom left.
        let button = [CGRect(x: 937, y: 427, width: 40, height: 17)]
        let windowHeight: CGFloat = 900
        XCTAssertTrue(ClickRegions.contains(button, pointInWindow: CGPoint(x: 950, y: 900 - 435), windowHeight: windowHeight))
        XCTAssertFalse(ClickRegions.contains(button, pointInWindow: CGPoint(x: 950, y: 435), windowHeight: windowHeight))
        XCTAssertFalse(ClickRegions.contains([], pointInWindow: CGPoint(x: 950, y: 465), windowHeight: windowHeight))
    }
}

final class UpdateTargetTests: XCTestCase {
    func testABuildReplacesTheRunningApp() {
        let appURL = URL(fileURLWithPath: "/Applications/LeagueasyMode.app")
        XCTAssertFalse(UpdateTarget.isTranslocated(appURL))
        XCTAssertEqual(UpdateTarget.installURL(runningAppURL: appURL), appURL)
    }

    func testAnAppRunFromMacOSsReadOnlyCopyIsUpdatedInApplications() {
        // Opened where the browser's download was unzipped, the app runs from a copy like this.
        let translocated = URL(
            fileURLWithPath: "/private/var/folders/ab/xyz/T/AppTranslocation/1234-ABCD/d/LeagueasyMode.app"
        )
        XCTAssertTrue(UpdateTarget.isTranslocated(translocated))
        XCTAssertEqual(
            UpdateTarget.installURL(runningAppURL: translocated).path, "/Applications/LeagueasyMode.app"
        )
    }
}
