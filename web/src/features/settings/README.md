# Settings feature (`src/features/settings`)

Owner: settings team. Entry: `SettingsPage` (route `#/settings`). `AppearanceSection` (theme: System /
Light / Dark via `useTheme`; also on the rail) and `SignOutSection` (the only sign-out on phone; keep it
last) are finished. Add the remaining sections between them in this order, each as a section header
(title-l) plus a `Card padding="tight"` of rows.

Reference behaviour: `app/static/index.html` on `main` (Settings pane markup, `loadSessions`,
`revokeSession`, `openConnect`, `loadApkInfo`, `uploadApk`, the vocabulary editor). Visual target:
`shot-settings-*` and `shot-settings-more-*`.

## What to build (from SPEC.md)

- **Vocabulary** (`useVocabulary`, `useSaveVocabulary`, `useImportVocabulary`,
  `parseVocabularyText`): explanation text with the `Plaud Bridge = Plogged Bridge, Plod Bridge`
  example, a small filter `TextField` ("Find a term") that narrows the visible lines, the count
  "437 terms · 52 with corrections", the borderless tonal mono text area
  (`TextField multiline tonal mono`), dirty tracking (Save / Revert disabled until the text differs
  from `editor_text`; "Saved · applies to new transcriptions" when clean), ignored-line count from
  `parseVocabularyText`, **Import…** (text button; file picker for a `.txt`/`.md` list, merged via
  import). Unsaved changes warn before navigating away.
- **Signed-in computers** (`useSessions`, `useRevokeSession`): one row per session with a laptop
  glyph, label ("Web browser" when null), `StatusChip tone="ok"` "this computer" for `current`,
  "Signed in {fmtWhen} · last used {fmtWhen}", text-danger **Sign out** with `ConfirmDialog danger`
  ("Sign out this computer?"). Empty: "No computers signed in with a QR code. Tokens entered by
  hand are not listed." 404: "Your server does not list signed-in computers yet." Refresh icon.
- **Phone**: "Connect a phone" row with a tonal button that opens a `Dialog` showing a QR of the
  connection payload exactly as `openConnect` builds it today (same encoder: `qrModel` in
  `@/lib/qr`), the login link `location.origin + '/#token=' + encodeURIComponent(token)` and the
  token in copyable fields (`copyText`). Clear the QR from the DOM when the dialog closes.
- **Android app** (`useApkInfo`, `useUploadApk`, `useDeleteApk`, `fetchApkBlob`): version, build,
  size (`fmtSize`), uploaded `fmtWhen`, notes, outlined **Download APK** (blob download via
  `downloadBlob`), text **Copy checksum**, "Upload a new version" row expanding to a form
  (file, version code, version name, min SDK, notes) with `LinearProgress` from `onProgress`, and
  text-danger **Remove** with confirm. Empty: "No app hosted yet" with the upload form.

## Where things go

```
settings/
  SettingsPage.tsx        route component: sections in order
  AppearanceSection.tsx   done
  vocabulary/             VocabularySection, useVocabularyEditor (dirty state, filter, counts)
  sessions/               SessionsSection
  phone/                  ConnectPhoneDialog, PhoneSection
  apk/                    AndroidAppSection, UploadApkForm
  *.test.tsx              MSW-backed tests (fixtures: vocabulary, sessionCurrent, apkInfo)
```

Errors: `errorMessage(err, fallback)` through `useSnackbar()`; inline for form validation.
