# Plaud Bridge web dashboard

React 18 + TypeScript (strict) + Vite + Tailwind v4, following Material 3. The design system
lives in `src/components` and `src/theme`; the component gallery (below) is the visual reference.
It replaced a vanilla dashboard, and the rule from that migration still holds: everything must
keep working, in user words, on desktop, on a phone and inside the Android app's WebView.

## Commands

```sh
cd web
npm ci                 # install from the lockfile
npm run dev            # http://localhost:5173/static/  (/api is proxied to http://127.0.0.1:8090)
npm run dev -- --host  # reachable from other machines (a phone, a remote browser)
npm run build          # tsc -b && vite build → ../app/static
npm test               # vitest (jsdom + testing-library + msw)
npm run lint           # eslint + prettier --check
npm run format         # prettier --write
```

Dev sign-in: the QR flow works against the live server; or paste a token from `PB_AUTH_TOKENS`.
Component gallery for visual QA: `#/dev/components` (dev server only, never in the production
bundle).

## Architecture

```
index.html            pre-paint theme script (?theme= > localStorage pb_theme > system), favicon
src/
  main.tsx            consumes #token=, rewrites legacy hashes, mounts <App/>
  App.tsx             providers: QueryClient → Theme → Embedded → Snackbar → Auth → HashRouter
  theme/              tokens.css (M3 colour roles via light-dark()), theme.css (Tailwind @theme
                      mapping, type scale, utilities, fonts, base), ThemeProvider/useTheme
  components/         the design system, one folder per component (index.tsx + <Name>.test.tsx)
  api/                client, zod types, query keys, TanStack hooks (see api/README.md)
  features/
    auth/             AuthProvider/useAuth, Gate (QR + token), useQrLogin, consumeLoginFragment
    shell/            AppShell (rail / bottom nav / embedded), routes (lazy sections), RouteFallback,
                      SectionAppBar, EmbeddedProvider/useEmbedded, bridge re-export, legacyHash
    recordings/       list, detail (lazy), player, actions  (README inside)
    automations/      banner, rules + editor, Try it, activity  (README inside)
    settings/         appearance, vocabulary, sessions, phone, Android app, sign out  (README inside)
  lib/                format (durations, friendly times), storage (never-throw wrappers + keys),
                      breakpoints (useIsDesktop, 840 px), bridge (Android bridge, clipboard,
                      download, share, readFileText), qr (toqr model), cn
  dev/                ComponentGallery (dev-only route)
  test/               msw server + handlers, fixtures, renderWithProviders
public/fonts/         roboto-flex, roboto, roboto-mono (woff2, latin subsets; committed)
public/favicon.svg
```

Layers, top to bottom: `features` → `components` → `lib` (and `api`, which only depends on `lib`).
A component never imports from a feature; if a component needs something feature-ish (the
clipboard bridge, say), the thing moves down into `lib/`.

### Data flow

- Every server call goes through `src/api` (fetch wrapper → zod schema → TanStack Query hook).
  Features never call `fetch`. Polling cadences and invalidation live in the hooks, so a screen
  just renders `query.data` and calls `mutation.mutate`.
- The player is a small external store (`features/recordings/player/playerStore.ts`) wrapping one
  `<audio>` element, read with `usePlayer` / `usePlayerSelector`. It survives route changes inside
  the Recordings section and resets when the section is left.
- List search/filter state lives in a module store (`useListState`) so the phone's list → detail →
  back round trip keeps it.

### Code splitting

Recordings (the first screen) ships in the main bundle. Loaded on demand, one chunk each:
the recording detail (`RecordingDetail`, opened from the list), the Automations and Settings
pages (`Suspense` with `RouteFallback`: section bar + skeleton rows), the markdown renderer
(react-markdown + remark-gfm, behind `Markdown`; plain paragraphs show until it arrives) and the
dev gallery. Every lazy boundary sits inside `LoadBoundary` (an `ErrorBoundary` showing
`LoadFailed` with Reload / Try again) so a chunk that cannot be fetched after a deployment never
takes the app down; `Markdown` falls back to its plain paragraphs. `npm run build` prints the chunk
sizes; keep the main chunk well under 150 KB gzipped.

## Conventions

- **Tokens, not colours.** Use the Tailwind names mapped in `theme/theme.css`
  (`bg-surface-container-high`, `text-on-surface-variant`, `rounded-lg`, `shadow-e2`,
  `text-title-m`, `ease-standard dur-medium`). Never a hex value in a component. Light/dark is
  handled by `light-dark()` in `tokens.css`; you do not write `dark:` for colours (it exists and
  follows `html[data-theme]` if you need a structural difference).
- **One breakpoint**: 840 px. `md:` in Tailwind is remapped to it; in code use `useIsDesktop()`.
- **User words only.** No route names, model ids, env vars, HTTP status codes or exception text
  in the UI. Errors go through `errorMessage(err, 'Couldn't …')` from `@/api` into `useSnackbar()`.
- **Status words only while in flight**; finished recordings show nothing. Destructive actions
  are `variant="danger"` buttons placed to the right and confirmed with `ConfirmDialog danger`
  (its confirming button is `Button variant="danger-filled"`, error / on-error in both themes).
- **Accessibility**: every interactive component has a role, a name and a visible focus ring;
  lists, menus, dialogs, radios, selects and tabs are keyboard operable. Keep it that way in
  features. Icon-only buttons take a `label`.
- **Dialogs**: `Dialog size="sm|md|lg"` (400 / 560 / 720 px); `fullScreen` makes a form dialog
  fill the phone with a top bar (close glyph, title, actions). The body scrolls; title and
  buttons stay put. Menus opened inside a dialog (a `Select`, a `Popover`) portal into the dialog
  automatically so they stay usable in the top layer.
- **Layout variables** set by the shell: `--content-bottom-pad` (bottom nav / Android tab bar),
  `--content-top-pad` (16 px when embedded), `--snackbar-bottom`. A section = `<SectionAppBar
title=…/>` + a scroll container with `pt-(--content-top-pad) pb-(--content-bottom-pad)`.
  `--field-bg` is the colour behind floating text-field labels; `Card` and `Dialog` set it.
- **Storage keys** are listed in `lib/storage.ts` (`STORAGE_KEYS`). Do not invent new ones without
  adding them there.
- **Imports** use the `@/` alias (`@/components`, `@/api`, `@/lib/format`). Prefer the folder
  import (`@/components/Button`) inside components themselves, the barrel elsewhere.
- **Formatting**: Prettier (`npm run format`); ESLint with react-hooks rules; no warnings.

## Adding a component

1. `src/components/Thing/index.tsx`: export `Thing` and `ThingProps`. Type every prop; document
   variants in the JSDoc; use `cn()` and token utilities; forward `className` and native attributes;
   `forwardRef` when the parent may need the DOM node (anchors, focus).
2. `src/components/Thing/Thing.test.tsx`: at least one test per variant/behaviour with
   `@testing-library/react` (roles and names, not class names, where possible).
3. Export it from `src/components/index.ts` and add it to `src/dev/ComponentGallery.tsx` in
   every variant. Open `#/dev/components` in both themes.
4. If a feature had a local wrapper doing the same job, delete the wrapper and use the component.

## Adding an icon

Icons are Material Symbols Rounded, one import per glyph in `src/components/Icon/icons.ts` so only
the icons in use ship. Add a line there (file name = Material name; aliases such as `laptop` →
`laptop_windows` are allowed) and it becomes a valid `IconName` everywhere.

## Adding an API hook

See `src/api/README.md`: schema in `types.ts`, key in `keys.ts`, hook in `hooks/*.ts`, MSW
handler in `src/test/msw.ts`, test.

## Adding a route or a feature

1. Feature code lives in `src/features/<name>/` with an `index.ts` and a `README.md`
   (layout, rules kept from the old dashboard, hooks used). The page component renders its own
   `SectionAppBar` and scroll container.
2. Add the route in `src/features/shell/routes.tsx` under the `<AppShell/>` layout route. New
   sections are lazy (`lazy(() => import('@/features/<name>').then(m => ({ default: m.Page })))`)
   inside `<Suspense fallback={<RouteFallback title=…/>}>`.
3. A new top-level section also needs an entry in `SECTIONS`, `SECTION_PATH` and
   `sectionForPath` in `AppShell.tsx` (rail + bottom nav), a `SectionKey` in
   `EmbeddedProvider.tsx` (so `?tab=` can select it) and, if the old dashboard had a hash for it,
   a rewrite in `legacyHash.ts`.
4. Tests: hook/integration tests with MSW against the documented API shapes, next to the code.

## Build, serving and deploy

- `npm run build` runs `tsc -b` then Vite with `base: '/static/'` and writes to `../app/static`
  (`index.html`, hashed `assets/*`, `fonts/*`, `favicon.svg`). The folder is git-ignored.
- `app/main.py` mounts `app/static` at `/static` and serves its `index.html` at `/`; both tolerate
  a missing build in development.
- The Docker image is multi-stage: `node:22-alpine` runs `npm ci && npm run build` from the
  lockfile, then the Python stage copies `app/static` in. Nothing is fetched at runtime (fonts and
  icons are bundled). Deploy is unchanged: `docker compose build -q && docker compose up -d`.
- Before committing: `npm run lint`, `npm test`, `npm run build`, the Python tests, and a Codex
  review (`codex review --uncommitted`); fix must/should findings.

## Embedded mode (the Android app)

The app loads `/?embedded=1&tab=<recordings|automations|settings>&theme=<light|dark>#/…` in a
WebView. Contract:

- `embedded=1`: no rail, no bottom nav, no section app bars (the app draws its own chrome);
  `html[data-embedded]` is set; content gets `--content-top-pad` 16 px and
  `--content-bottom-pad` 120 px so the app's floating tab bar never covers it. A recording opened
  from the list keeps its Back button.
- `tab=`: the section to open when the URL has no hash route. The app changes tabs by loading a
  new URL (or setting the hash to `#/automations` etc.).
- `theme=`: applied before first paint (index.html) and by `ThemeProvider`, never saved to
  `pb_theme`.
- Sign-in: the app injects the token through a `#token=<token>` login link, which `main.tsx`
  consumes and scrubs from the URL before anything renders; the token is adopted only after the
  server confirms it.
- Native bridge: the app injects `window.PlaudBridgeApp` with `copyText(text)` (WebViews often
  cannot reach `navigator.clipboard`; the app shows its own toast) and
  `shareMarkdown(name, markdown)` (WebViews cannot download blobs; the app opens its share sheet).
  Use `copyText` / `shareMarkdown` / `downloadBlob` from `@/lib/bridge` (re-exported by
  `@/features/shell`); they fall back to web APIs outside the app.

## Storage keys

| Where          | Key                     | Holds                                                                  |
| -------------- | ----------------------- | ---------------------------------------------------------------------- |
| localStorage   | `pb_token`              | the bearer token (cleared on sign out)                                 |
| localStorage   | `pb_theme`              | `system` / `light` / `dark` (not written when `?theme=` forces one)    |
| localStorage   | `pb_speed`              | playback speed `1` / `1.5` / `2`                                       |
| sessionStorage | `pb_login_req`          | the pending QR login request `{id, expires_at, poll_seconds}`          |
| sessionStorage | `pb.routeKey.<recId>`   | Idempotency-Key of an in-flight "run automations" (a retry replays it) |
| sessionStorage | `pb.routeInstr.<recId>` | the instructions typed for that run, kept across a reload              |

The Android app and the old dashboard share these names; changing one is a migration.
