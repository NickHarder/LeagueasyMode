// swift-tools-version: 6.0
// The macOS overlay app: a transparent, click-through window over League that shows the engine's
// page. `swift run LeagueasyOverlay` from this directory starts it, and it starts the engine.
//
// Swift 6's language mode, the tools version's default, checks concurrency in full: a call that
// could race is an error, not a warning.

import PackageDescription

let strictSettings: [SwiftSetting] = [
    .enableUpcomingFeature("ExistentialAny"),
]

let package = Package(
    name: "LeagueasyOverlay",
    platforms: [.macOS(.v13)],
    targets: [
        // What the app decides, without AppKit, so that it can be tested on its own.
        .target(name: "OverlayCore", swiftSettings: strictSettings),
        .executableTarget(
            name: "LeagueasyOverlay",
            dependencies: ["OverlayCore"],
            swiftSettings: strictSettings
        ),
        .testTarget(
            name: "OverlayCoreTests",
            dependencies: ["OverlayCore"],
            swiftSettings: strictSettings
        ),
    ]
)
