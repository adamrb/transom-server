# Settings feature (`src/features/settings`)

Owner: settings team. Entry: `SettingsPage` (route `#/settings`), which stacks `SETTINGS_SECTIONS` in
order: Appearance, Vocabulary, Signed-in computers, Phone, Android app, This computer (sign out; keep
it last, it is the only sign-out on phone). Embedded in the Android app there is no section app bar.

Reference behaviour: `app/static/index.html` on `main` (`loadVocabulary`/`saveVocabulary`/
`importVocabulary`, `loadSessions`/`revokeSession`, `openConnect`, `loadApkInfo`/`uploadApk`).
Visual target: `shot-settings-*` and `shot-settings-more-*`; what shipped: `react-b3-*`.

## Layout

```
settings/
  SettingsPage.tsx          route component; SETTINGS_SECTIONS
  SettingsSection.tsx       SettingsSection (title-l header + optional actions, `card` wraps a tight Card)
                            SettingsRow (flat ListItem with a 40 px icon avatar)
  AppearanceSection.tsx     theme: System / Light / Dark
  SignOutSection.tsx        "This computer" sign out
  shared/                   CopyField (read-only value + copy, `secret` masks with dots),
                            FilePicker (labelled file input as an outlined button), readFileText
  vocabulary/
    VocabularySection.tsx   the card: help text, filter, counts, List/Text toggle, footer with
                            status + Import… / Revert / Save
    useVocabularyEditor.ts  dirty tracking over the server's editor_text (see below)
    VocabularyList.tsx      rows (term, "Heard as …", edit, remove) in a 420 px scroll box + Add a term
    VocabularyRowEditor.tsx inline add/edit form (term, comma-separated mis-hearings, validation)
    ImportDialog.tsx        paste or pick a file → POST /vocabulary/import → "N terms added"
  sessions/
    SessionsSection.tsx     list, refresh, revoke with ConfirmDialog, empty / older-server notes
    SessionRow.tsx          label ("Web browser" when null), "this computer" badge, signed in / last used
  phone/
    ConnectPhoneSection.tsx row + ConnectPhoneDialog (QR, server address, masked token, sign-in link,
                            warning banner)
    QrCard.tsx              black-on-white QR via `qrModel` (toqr, EC M, 4-module quiet zone)
    connectPayload.ts       `{"v":1,"url":origin,"token":token}` and `origin/#token=…`, byte for byte
                            what the old dashboard produced
  apk/
    AndroidAppSection.tsx   hosted version card (Download APK, Copy checksum, Remove) + Upload row
    ApkUploadDialog.tsx     file, version code, version name, notes; XHR progress; `validateApkForm`
  *.test.tsx                MSW-backed tests next to each folder
```

## Vocabulary editor model

The server owns the text format (`Term = mis-hearing, mis-hearing`, `#` notes) and returns it as
`editor_text`. The editor keeps one draft **string**; the list view is a projection of that string
(`parseVocabularyLines` in `api/hooks/vocabulary.ts`), so list edits rewrite exactly one line and
notes/blank lines survive. The draft is `null` while it follows the server: a refetch can never
overwrite local edits, and editing back to the server text un-pins it (`vocabDirty()` semantics from
the old dashboard). Save PUTs the parsed entries with each term's `source` carried over from the loaded
vocabulary (imported terms stay imported), then adopts the server's normalised text. Lines with nothing
before the equals sign are counted in the footer and dropped on save, like before. A `beforeunload`
prompt guards unsaved edits.

## Conventions

Errors go through `errorMessage(err, fallback)` into `useSnackbar()`; form validation is inline.
404 on `/sessions` or `/vocabulary` means an older server: say so in user words, never a status code.
Destructive buttons are `variant="danger"`, placed right, and confirmed with `ConfirmDialog danger`.
