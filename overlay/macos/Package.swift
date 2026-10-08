// swift-tools-version: 5.10
// The macOS overlay app: a transparent, click-through window over League that shows the engine's
// page. `swift run LeagueasyOverlay` from this directory starts it, and it starts the engine.

import PackageDescription

let strictSettings: [SwiftSetting] = [
    .enableUpcomingFeature("StrictConcurrency"),
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
