import Carbon.HIToolbox

/// A shortcut that works whichever app is in front, through Carbon's hot keys.
///
/// Carbon hot keys need no Accessibility or Input Monitoring permission, unlike a global event
/// monitor, because the system delivers only the registered combination to the app.
final class GlobalHotKey {
    /// "LEAG", which tells this app's hot keys apart from any other's.
    private static let signature = OSType(0x4C45_4147)

    private let action: () -> Void
    private var hotKeyReference: EventHotKeyRef?
    private var handlerReference: EventHandlerRef?

    /// Registers the shortcut; returns nil when the system refuses it, as when another app has it.
    ///
    /// - Parameters:
    ///   - keyCode: The key, as a virtual key code (`kVK_ANSI_L`).
    ///   - modifiers: The modifier keys, as Carbon flags (`cmdKey | optionKey | controlKey`).
    ///   - action: What to do when the shortcut is pressed; called on the main thread.
    init?(keyCode: UInt32, modifiers: UInt32, action: @escaping () -> Void) {
        self.action = action
        var pressedEventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)
        )
        let unretainedSelf = Unmanaged.passUnretained(self).toOpaque()
        let installStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, _, userData -> OSStatus in
                guard let userData else {
                    return OSStatus(eventNotHandledErr)
                }
                Unmanaged<GlobalHotKey>.fromOpaque(userData).takeUnretainedValue().action()
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
        let hotKeyIdentifier = EventHotKeyID(signature: GlobalHotKey.signature, id: 1)
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
