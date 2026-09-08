/// <reference types="vite/client" />

/** The Android app's native bridge, injected into the WebView as window.PlaudBridgeApp. */
interface PlaudBridgeNative {
  /** Copy text to the clipboard (WebViews often cannot reach navigator.clipboard). */
  copyText?: (text: string) => void;
  /** Share a markdown file through the Android share sheet (WebViews cannot download blobs). */
  shareMarkdown?: (name: string, markdown: string) => void;
}

interface Window {
  PlaudBridgeApp?: PlaudBridgeNative;
}
