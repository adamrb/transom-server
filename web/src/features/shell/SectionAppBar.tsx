import { IconButton } from '@/components/IconButton';
import { TopAppBar, type TopAppBarProps } from '@/components/TopAppBar';
import { useIsDesktop } from '@/lib/breakpoints';
import { useTheme } from '@/theme';
import { useEmbedded } from './EmbeddedProvider';

export interface SectionAppBarProps extends Omit<TopAppBarProps, 'variant' | 'as'> {
  title: string;
}

/**
 * The large top app bar of a section (Recordings, Automations, Settings). Hidden when embedded
 * (the Android app draws its own). On phone it carries the theme toggle, since there is no rail.
 */
export function SectionAppBar({ title, actions, ...rest }: SectionAppBarProps) {
  const { embedded } = useEmbedded();
  const desktop = useIsDesktop();
  const { resolved, toggle } = useTheme();
  if (embedded) return null;
  return (
    <TopAppBar
      title={title}
      variant="large"
      as="h1"
      actions={
        <>
          {actions}
          {!desktop && (
            <IconButton
              icon={resolved === 'dark' ? 'light_mode' : 'dark_mode'}
              label={resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              onClick={toggle}
            />
          )}
        </>
      }
      {...rest}
    />
  );
}
