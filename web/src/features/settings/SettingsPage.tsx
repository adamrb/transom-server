import type { ComponentType } from 'react';
import { SectionAppBar } from '@/features/shell/SectionAppBar';
import { AppearanceSection } from './AppearanceSection';
import { SignOutSection } from './SignOutSection';
import { VocabularySection } from './vocabulary/VocabularySection';
import { SessionsSection } from './sessions/SessionsSection';
import { ConnectPhoneSection } from './phone/ConnectPhoneSection';
import { AndroidAppSection } from './apk/AndroidAppSection';

/** The sections, in the order they stack. Sign out stays last (the only sign-out on phone). */
export const SETTINGS_SECTIONS: { key: string; component: ComponentType }[] = [
  { key: 'appearance', component: AppearanceSection },
  { key: 'vocabulary', component: VocabularySection },
  { key: 'sessions', component: SessionsSection },
  { key: 'phone', component: ConnectPhoneSection },
  { key: 'android', component: AndroidAppSection },
  { key: 'sign-out', component: SignOutSection },
];

/**
 * Settings: appearance, vocabulary, signed-in computers, connect a phone, the Android app and
 * sign out. Embedded in the Android app there is no app bar (the app draws its own).
 */
export function SettingsPage() {
  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="settings-title">
      <SectionAppBar title="Settings" id="settings-title" />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-(--content-top-pad) pb-(--content-bottom-pad) max-md:px-4">
        <div className="mx-auto max-w-[860px]">
          {SETTINGS_SECTIONS.map(({ key, component: Section }) => (
            <Section key={key} />
          ))}
        </div>
      </div>
    </section>
  );
}
