import Carbon.HIToolbox

/// A shortcut that works whichever app is in front, through Carbon's hot keys.
///
/// Carbon hot keys need no Accessibility or Input Monitoring permission, unlike a global event
/// monitor, because the system delivers only the registered combination to the app. Every hot key
/// installs a handler for every hot-key press, so each one checks the press is its own and passes
/// any other on to the next handler.
final class GlobalHotKey {
    /// "LEAG", which tells this app's hot keys apart from any other's.
    private static let signature = OSType(0x4C45_4147)

    private let identifier: UInt32
    private let action: @MainActor @Sendable () -> Void
    private var hotKeyReference: EventHotKeyRef?
    private var handlerReference: EventHandlerRef?

    /// Registers the shortcut; returns nil when the system refuses it, as when another app has it.
    ///
    /// - Parameters:
    ///   - identifier: This app's number for the shortcut, different for each one.
    ///   - keyCode: The key, as a virtual key code (`kVK_ANSI_L`).
    ///   - modifiers: The modifier keys, as Carbon flags (`cmdKey | optionKey | controlKey`).
    ///   - action: What to do when the shortcut is pressed; called on the main thread.
    init?(
        identifier: UInt32,
        keyCode: UInt32,
        modifiers: UInt32,
        action: @escaping @MainActor @Sendable () -> Void
    ) {
        self.identifier = identifier
        self.action = action
        var pressedEventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)
        )
        let unretainedSelf = Unmanaged.passUnretained(self).toOpaque()
        let installStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, userData -> OSStatus in
                guard let event, let userData else {
                    return OSStatus(eventNotHandledErr)
                }
                var pressedHotKeyIdentifier = EventHotKeyID()
                let parameterStatus = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &pressedHotKeyIdentifier
                )
                let hotKey = Unmanaged<GlobalHotKey>.fromOpaque(userData).takeUnretainedValue()
                guard
                    parameterStatus == OSStatus(noErr),
                    pressedHotKeyIdentifier.signature == GlobalHotKey.signature,
                    pressedHotKeyIdentifier.id == hotKey.identifier
                else {
                    return OSStatus(eventNotHandledErr)
                }
                // The application's event target delivers hot keys on the main thread.
                let action = hotKey.action
                MainActor.assumeIsolated { action() }
                return OSStatus(noErr)
            },
            1,
            &pressedEventType,
            unretainedSelf,
            &handlerReference
        )
        guard installStatus == OSStatus(noErr) else {
            return nil
        }
        let hotKeyIdentifier = EventHotKeyID(signature: GlobalHotKey.signature, id: identifier)
        let registerStatus = RegisterEventHotKey(
            keyCode, modifiers, hotKeyIdentifier, GetApplicationEventTarget(), 0, &hotKeyReference
        )
        // On failure, deinit still runs (every property is set), and removes the handler.
        guard registerStatus == OSStatus(noErr) else {
            return nil
        }
    }

    deinit {
        if let hotKeyReference {
            UnregisterEventHotKey(hotKeyReference)
        }
        if let handlerReference {
            RemoveEventHandler(handlerReference)
        }
    }
}
