/**
 * Test render helpers: wrap a tree in the app's providers with a fresh QueryClient (no retries).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { ThemeProvider } from '@/theme';
import { SnackbarProvider } from '@/components/Snackbar';
import { tokenStore } from '@/api/token';
import { TEST_TOKEN } from './msw';

export function makeTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 }, mutations: { retry: false } },
  });
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Initial hash-less route for MemoryRouter, e.g. '/rec/abc'. */
  route?: string;
  /** Store the test token first (default true) so guarded MSW handlers answer. */
  signedIn?: boolean;
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', signedIn = true, queryClient, ...options }: RenderWithProvidersOptions = {},
) {
  if (signedIn) tokenStore.set(TEST_TOKEN);
  const qc = queryClient ?? makeTestQueryClient();
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <ThemeProvider search="">
        <SnackbarProvider>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </SnackbarProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
  return { queryClient: qc, ...render(ui, { wrapper: Wrapper, ...options }) };
}
