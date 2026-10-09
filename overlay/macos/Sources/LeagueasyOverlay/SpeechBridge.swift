import AVFoundation
import OverlayCore
import WebKit

/// Speaks the callouts the overlay page hands over, in macOS's own voice. The page sends one only
/// when the player turned speech on in the settings.
final class SpeechBridge: NSObject, WKScriptMessageHandler {
    private let synthesizer = AVSpeechSynthesizer()

    func userContentController(
        _ userContentController: WKUserContentController, didReceive message: WKScriptMessage
    ) {
        guard let text = SpokenCallout.text(fromMessageBody: message.body) else {
            return
        }
        synthesizer.speak(AVSpeechUtterance(string: text))
    }
}
