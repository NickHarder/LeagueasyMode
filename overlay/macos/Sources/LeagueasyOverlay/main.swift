// The app's entry point: a menu bar app with no Dock icon, whose delegate does the rest.

import AppKit

let application = NSApplication.shared
let applicationDelegate = AppDelegate()
application.delegate = applicationDelegate
application.setActivationPolicy(.accessory)
application.run()
