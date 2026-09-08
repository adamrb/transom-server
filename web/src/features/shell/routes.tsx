import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { LinearProgress } from '@/components/LinearProgress';
import { RecordingsPage } from '@/features/recordings';
import { AppShell } from './AppShell';
import { LoadBoundary, RouteFallback } from './RouteFallback';

// Recordings is the first screen, so it ships in the main bundle; the other sections load on
// first visit (one chunk each, cached by the browser afterwards).
const AutomationsPage = lazy(() =>
  import('@/features/automations').then((m) => ({ default: m.AutomationsPage })),
);
const SettingsPage = lazy(() => import('@/features/settings').then((m) => ({ default: m.SettingsPage })));

// Visual QA gallery of every component; development only (never in the production bundle).
const ComponentGallery = import.meta.env.DEV ? lazy(() => import('@/dev/ComponentGallery')) : null;

/**
 * Hash routes:
 *   #/                 recordings list (desktop: with the getting-started pane)
 *   #/rec/:id          a recording open (desktop: list + detail; phone: full-screen detail)
 *   #/automations
 *   #/settings
 *   #/dev/components   component gallery (dev only)
 * Legacy `#rec/<id>`, `#automations`, `#settings` are rewritten in main.tsx.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<RecordingsPage />} />
        <Route path="/rec/:id" element={<RecordingsPage />} />
        <Route
          path="/automations"
          element={
            <LoadBoundary what="Automations">
              <Suspense fallback={<RouteFallback title="Automations" />}>
                <AutomationsPage />
              </Suspense>
            </LoadBoundary>
          }
        />
        <Route
          path="/settings"
          element={
            <LoadBoundary what="Settings">
              <Suspense fallback={<RouteFallback title="Settings" />}>
                <SettingsPage />
              </Suspense>
            </LoadBoundary>
          }
        />
        {ComponentGallery && (
          <Route
            path="/dev/components"
            element={
              <LoadBoundary what="the component gallery">
                <Suspense fallback={<LinearProgress label="Loading" />}>
                  <ComponentGallery />
                </Suspense>
              </LoadBoundary>
            }
          />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
