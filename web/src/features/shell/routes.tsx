import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { LinearProgress } from '@/components/LinearProgress';
import { RecordingsPage } from '@/features/recordings';
import { AutomationsPage } from '@/features/automations';
import { SettingsPage } from '@/features/settings';
import { AppShell } from './AppShell';

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
        <Route path="/automations" element={<AutomationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {ComponentGallery && (
          <Route
            path="/dev/components"
            element={
              <Suspense fallback={<LinearProgress label="Loading" />}>
                <ComponentGallery />
              </Suspense>
            }
          />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
