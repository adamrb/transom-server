# Plaud Bridge web dashboard

React 18 + TypeScript (strict) + Vite + Tailwind v4, following Material 3. The
design spec is `SPEC.md` / `RATIONALE.md` in the design hand-off; the functional reference is the
vanilla dashboard that lived at `app/static/index.html` on `main` (read it as the spec for what
every screen must keep doing).

The build lands in `../app/static`, which the FastAPI server mounts at `/static` and serves as `/`.
The Docker image builds it (multi-stage, `node:22-alpine`, `npm ci && npm run build`); nothing is
fetched at runtime (fonts and icons are bundled).

## Commands

```sh
cd web
npm ci                 # install from the lockfile
npm run dev            # http://localhost:5173, /api proxied to http://127.0.0.1:8090
npm run dev -- --host  # reachable from other machines (Neko, a phone)
npm run build          # tsc -b && vite build → ../app/static
npm test               # vitest (jsdom + testing-library + msw)
npm run lint           # eslint + prettier --check
npm run format         # prettier --write
```

Dev sign-in: the QR flow works against the live server; or paste a token from `PB_AUTH_TOKENS`.
Component gallery for visual QA: `#/dev/components` (dev server only).

## Layout

```
src/
  main.tsx            consumes #token=, rewrites legacy hashes, mounts <App/>
  App.tsx             providers: QueryClient → Theme → Embedded → Snackbar → Auth → HashRouter
  theme/              tokens.css (M3 colour roles via light-dark()), theme.css (Tailwind @theme
                      mapping, type scale, utilities, fonts, base), ThemeProvider/useTheme
  components/         the design system, one folder per component (index.tsx + <Name>.test.tsx)
  api/                client, zod types, query keys, TanStack hooks (see api/README.md)
  features/
    auth/             AuthProvider/useAuth, Gate (QR + token), useQrLogin, consumeLoginFragment
    shell/            AppShell (rail / bottom nav / embedded), routes, SectionAppBar,
                      EmbeddedProvider/useEmbedded, bridge (copyText, shareMarkdown), legacyHash
    recordings/       placeholder + README (recordings team)
    automations/      placeholder + README (automations team)
    settings/         AppearanceSection (done) + placeholder + README (settings team)
  lib/                format (durations, friendly times), storage (never-throw wrappers + keys),
                      breakpoints (useIsDesktop, 840 px), qr (toqr model), cn
  dev/                ComponentGallery (dev-only route)
  test/               msw server + handlers, fixtures, renderWithProviders
public/fonts/         roboto-flex, roboto, roboto-mono (woff2, latin subsets; committed)
```

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
  are `variant="danger"` buttons placed to the right and confirmed with `ConfirmDialog danger`.
- **Accessibility**: every interactive component has a role, a name and a visible focus ring;
  lists, menus, dialogs and tabs are keyboard operable. Keep it that way in features.
- **Layout variables** set by the shell: `--content-bottom-pad` (bottom nav / Android tab bar), `--content-top-pad` (16 px when embedded),
  `--snackbar-bottom`. A section = `<SectionAppBar title=…/>` + a scroll container with
  `pb-(--content-bottom-pad)`.
- **Storage keys** are listed in `lib/storage.ts` (`STORAGE_KEYS`). Do not invent new ones without
  adding them there.
- **Imports** use the `@/` alias (`@/components`, `@/api`, `@/lib/format`).

## Adding a component

1. `src/components/Thing/index.tsx`: export `Thing` and `ThingProps`. Type every prop; document
   variants in the JSDoc; use `cn()` and token utilities; forward `className` and native attributes;
   `forwardRef` when the parent may need the DOM node (anchors, focus).
2. `src/components/Thing/Thing.test.tsx`: at least one test per variant/behaviour with
   `@testing-library/react` (roles and names, not class names, where possible).
3. Export it from `src/components/index.ts` and add it to `src/dev/ComponentGallery.tsx` in
   every variant.

## Adding an API hook

See `src/api/README.md`: schema in `types.ts`, key in `keys.ts`, hook in `hooks/*.ts`, MSW
handler in `src/test/msw.ts`, test.

## Adding a route

Add it to `src/features/shell/routes.tsx` under the `<AppShell/>` layout route, and to
`SECTION_PATH` / `sectionForPath` in `AppShell.tsx` if it is a new top-level section (it then needs
a `NavDestination` in `SECTIONS`). Sections must render their own `SectionAppBar`.

## Embedded mode (Android WebView)

`/?embedded=1&tab=settings&theme=dark#/…`: no rail, no bottom nav, no section app bars; content
gets 120 px bottom padding for the app's tab bar; `tab=` picks the section when no hash route is
present; `theme=` is applied but never saved. The app injects `window.PlaudBridgeApp` with
`copyText(text)` and `shareMarkdown(name, markdown)`; use `copyText` / `shareMarkdown` from
`@/features/shell` which fall back to web APIs.
