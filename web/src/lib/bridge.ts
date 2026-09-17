/**
 * Inside the Android app the page gets a tiny native bridge (window.TransomApp) because a
 * WebView can neither download a blob nor, on some builds, reach navigator.clipboard. Elsewhere
 * the web APIs are used. Detection mirrors the vanilla dashboard exactly.
 *
 * Lives in lib/ (below components/) so design-system pieces such as CopyField can copy through
 * the bridge without reaching into a feature. `@/features/shell` re-exports it.
 */
export function appBridge(): TransomNative | null {
  if (typeof window === 'undefined') return null;
  // App builds before the 0.6.0 rename inject the bridge under its old name; keep accepting it
  // for one release so upgrading the server does not break copy/share in an older app.
  const legacy = (window as unknown as { PlaudBridgeApp?: TransomNative }).PlaudBridgeApp;
  const b = window.TransomApp ?? legacy;
  return typeof b === 'object' && b ? b : null;
}

export type CopyResult = 'copied' | 'bridge' | 'failed';

/**
 * Copy text: navigator.clipboard first, then the app bridge (which shows its own toast, so the
 * caller must not), then the execCommand fallback.
 */
export async function copyText(text: string): Promise<CopyResult> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return 'copied';
    }
    throw new Error('no clipboard api');
  } catch {
    const b = appBridge();
    if (b?.copyText) {
      b.copyText(text);
      return 'bridge';
    }
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = !!document.execCommand && document.execCommand('copy');
    } catch {
      ok = false;
    }
    ta.remove();
    return ok ? 'copied' : 'failed';
  }
}

/** Trigger a browser download of a blob. */
export function downloadBlob(blob: Blob, name: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export type ShareResult = 'bridge' | 'downloaded';

/** Markdown export: the app's share sheet when embedded, otherwise a .md download. */
export function shareMarkdown(name: string, markdown: string): ShareResult {
  const b = appBridge();
  if (b?.shareMarkdown) {
    b.shareMarkdown(name, markdown);
    return 'bridge';
  }
  downloadBlob(new Blob([markdown], { type: 'text/markdown' }), name);
  return 'downloaded';
}

/** Read a picked file as text. `Blob.text()` where it exists, FileReader in older WebViews. */
export function readFileText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('read failed'));
    reader.readAsText(file);
  });
}
