/**
 * The Android app's native bridge. The implementation lives in `@/lib/bridge` (so design-system
 * components can use it); this module keeps the feature-level import path.
 */
export {
  appBridge,
  copyText,
  downloadBlob,
  shareMarkdown,
  readFileText,
  type CopyResult,
  type ShareResult,
} from '@/lib/bridge';
