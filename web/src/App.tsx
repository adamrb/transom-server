import { useMemo, type ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { HashRouter } from 'react-router-dom';
import { createQueryClient } from '@/api/queryClient';
import { SnackbarProvider } from '@/components/Snackbar';
import { ThemeProvider } from '@/theme';
import { AuthProvider, Gate, useAuth } from '@/features/auth';
import { AppRoutes, EmbeddedProvider } from '@/features/shell';

export interface AppProps {
  /** Token from a `#token=` login link, consumed in main.tsx before anything rendered. */
  loginCandidate?: string;
}

/** Renders the gate while signed out, nothing while the stored token is being checked, else the app. */
function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === 'signed-out') return <Gate />;
  if (status === 'checking') return null;
  return <>{children}</>;
}

/**
 * Provider order matters: QueryClient (used by Auth), Theme (reads ?theme=), Embedded (reads
 * ?embedded=&tab=), Snackbar (used by everything), Auth (needs QueryClient), Router (needs Auth
 * because the shell's sign-out button uses it).
 */
export default function App({ loginCandidate = '' }: AppProps) {
  const queryClient = useMemo(createQueryClient, []);
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <EmbeddedProvider>
          <SnackbarProvider>
            <AuthProvider initialCandidate={loginCandidate}>
              <HashRouter>
                <AuthGate>
                  <AppRoutes />
                </AuthGate>
              </HashRouter>
            </AuthProvider>
          </SnackbarProvider>
        </EmbeddedProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
