/**
 * Speaking a callout. Inside the macOS app the page hands the text to the app, which speaks it in
 * macOS's voice (`SpeechBridge`); in a browser, as when developing against a replay, the browser's
 * own speech synthesis speaks it instead.
 */

/** One of the app's handlers of the page's messages, as WebKit exposes it. */
interface MessageHandler {
  postMessage(message: unknown): void;
}

declare global {
  interface Window {
    // The app's handlers: speech here, and where the click-to-mark buttons are (marking.ts).
    webkit?: {
      readonly messageHandlers?: {
        readonly leagueasymodeSpeak?: MessageHandler;
        readonly leagueasymodeClickRegions?: MessageHandler;
      };
    };
  }
}

/** Say a callout aloud. */
export function speak(text: string): void {
  const appVoice = window.webkit?.messageHandlers?.leagueasymodeSpeak;
  if (appVoice !== undefined) {
    appVoice.postMessage(text);
    return;
  }
  if ("speechSynthesis" in window) {
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}
