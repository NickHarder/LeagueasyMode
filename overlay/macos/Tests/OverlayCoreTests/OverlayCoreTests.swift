import Foundation
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
    }

    func testEachPageHasItsMenuTitle() {
        XCTAssertEqual(EnginePage.allCases.map(\.menuTitle), ["Last game\u{2026}", "Settings\u{2026}"])
    }
}
