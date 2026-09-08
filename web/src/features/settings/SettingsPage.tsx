import { EmptyState } from '@/components/EmptyState';
import { SectionAppBar } from '@/features/shell/SectionAppBar';
import { AppearanceSection } from './AppearanceSection';
import { SignOutSection } from './SignOutSection';

/**
 * Settings. Appearance is done (theme lives here and on the rail). The settings team adds
 * Vocabulary, Signed-in computers, Phone and Android app below it (see README.md).
 */
export function SettingsPage() {
  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="settings-title">
      <SectionAppBar title="Settings" id="settings-title" />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-(--content-top-pad) pb-(--content-bottom-pad) max-md:px-4">
        <div className="mx-auto max-w-[860px]">
          <AppearanceSection />
          <EmptyState
            compact
            icon="settings"
            headline="More settings coming soon"
            description="Vocabulary, signed-in computers, connecting a phone and the Android app are being built here."
          />
          <SignOutSection />
        </div>
      </div>
    </section>
  );
}
