/**
 * Speaking a callout. Inside the macOS app the page hands the text to the app, which speaks it in
 * macOS's voice (`SpeechBridge`); in a browser, as when developing against a replay, the browser's
 * own speech synthesis speaks it instead.
 */
/** Say a callout aloud. */
export function speak(text) {
    const appVoice = window.webkit?.messageHandlers?.leagueasymodeSpeak;
    if (appVoice !== undefined) {
        appVoice.postMessage(text);
        return;
    }
    if ("speechSynthesis" in window) {
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    }
}
