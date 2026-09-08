import { Avatar } from '@/components/Avatar';
import { Card } from '@/components/Card';
import { SegmentedButton } from '@/components/SegmentedButton';
import { useIsDesktop } from '@/lib/breakpoints';
import { useTheme, type ThemeChoice } from '@/theme';
import { useEmbedded } from '@/features/shell/EmbeddedProvider';

const OPTIONS = [
  { key: 'system', label: 'System', icon: 'contrast' },
  { key: 'light', label: 'Light', icon: 'light_mode' },
  { key: 'dark', label: 'Dark', icon: 'dark_mode' },
] as const;

/** Theme choice (System / Light / Dark). Ready for the settings team to keep as its first section. */
export function AppearanceSection() {
  const { theme, setTheme, forced } = useTheme();
  const { embedded } = useEmbedded();
  const desktop = useIsDesktop();
  return (
    <>
      <div className="mt-0 mb-3 flex items-center gap-3 first:mt-0 [&:not(:first-child)]:mt-7">
        <h2 className="m-0 flex-1 font-display text-title-l text-on-surface">Appearance</h2>
      </div>
      <Card padding="tight">
        <div className="flex flex-wrap items-center gap-4 py-3.5">
          <Avatar kind="icon" icon="palette" size={40} shape="rounded" />
          <div className="min-w-0 flex-1">
            <div className="text-body-l text-on-surface">Theme</div>
            <div className="text-body-m text-on-surface-variant">
              {embedded || forced
                ? 'Follows the phone while opened from the app'
                : 'Light, dark, or whatever your computer uses'}
            </div>
          </div>
          <SegmentedButton<ThemeChoice>
            label="Theme"
            value={theme}
            onChange={setTheme}
            options={[...OPTIONS]}
            fill={!desktop}
            className={!desktop ? 'my-1 basis-full' : undefined}
          />
        </div>
      </Card>
    </>
  );
}
