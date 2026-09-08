import { useEffect, type CSSProperties } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { BottomNav } from '@/components/BottomNav';
import { IconButton } from '@/components/IconButton';
import { NavRail, type NavDestination } from '@/components/NavRail';
import { useIsDesktop } from '@/lib/breakpoints';
import { cn } from '@/lib/cn';
import { useTheme } from '@/theme';
import { useAuth } from '@/features/auth';
import { EMBEDDED_BOTTOM_PAD, useEmbedded, type SectionKey } from './EmbeddedProvider';

export const SECTIONS: NavDestination<SectionKey>[] = [
  { key: 'recordings', label: 'Recordings', icon: 'graphic_eq' },
  { key: 'automations', label: 'Automations', icon: 'wand_stars' },
  { key: 'settings', label: 'Settings', icon: 'settings' },
];

export const SECTION_PATH: Record<SectionKey, string> = {
  recordings: '/',
  automations: '/automations',
  settings: '/settings',
};

export function sectionForPath(pathname: string): SectionKey {
  if (pathname.startsWith('/automations')) return 'automations';
  if (pathname.startsWith('/settings')) return 'settings';
  return 'recordings';
}

/**
 * The app frame: navigation rail (≥ 840 px) or bottom navigation (< 840 px), the section
 * content in an <Outlet>, and nothing at all around the content when embedded in the Android
 * app. Sets two CSS variables the sections and the snackbar read:
 *   --content-bottom-pad  space to leave under scrolling content (bottom nav / app tab bar)
 *   --content-top-pad     16 px when embedded (no app bar), else 0
 *   --snackbar-bottom     where the snackbar sits
 */
export function AppShell() {
  const desktop = useIsDesktop();
  const { embedded, initialTab } = useEmbedded();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { resolved, toggle } = useTheme();
  const { signOut } = useAuth();
  const section = sectionForPath(pathname);

  // Embedded: the app says which tab to show when no deep link was given.
  useEffect(() => {
    if (embedded && initialTab && pathname === '/' && initialTab !== 'recordings')
      navigate(SECTION_PATH[initialTab], { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const go = (key: SectionKey) => navigate(SECTION_PATH[key]);
  const showRail = desktop && !embedded;
  const showBottomNav = !desktop && !embedded;

  const vars = {
    '--content-bottom-pad': embedded
      ? `${EMBEDDED_BOTTOM_PAD}px`
      : showBottomNav
        ? 'calc(var(--bottom-nav-h) + 16px)'
        : '0px',
    '--snackbar-bottom': embedded ? '140px' : showBottomNav ? 'calc(var(--bottom-nav-h) + 16px)' : '24px',
    // No app bar when embedded: give the first section header some air, as the mockup does.
    '--content-top-pad': embedded ? '16px' : '0px',
  } as CSSProperties;

  return (
    <div
      id="app"
      data-section={section}
      data-embedded={embedded || undefined}
      className="flex h-full bg-surface"
      style={vars}
    >
      {showRail && (
        <NavRail
          destinations={SECTIONS}
          value={section}
          onChange={go}
          footer={
            <>
              <IconButton
                icon={resolved === 'dark' ? 'light_mode' : 'dark_mode'}
                label={resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
                iconSize={22}
                onClick={toggle}
              />
              <IconButton icon="logout" label="Sign out" iconSize={22} onClick={() => void signOut()} />
            </>
          }
        />
      )}
      <main className={cn('flex min-w-0 flex-1 flex-col', 'h-full min-h-0')}>
        <Outlet />
      </main>
      {showBottomNav && <BottomNav destinations={SECTIONS} value={section} onChange={go} />}
    </div>
  );
}
