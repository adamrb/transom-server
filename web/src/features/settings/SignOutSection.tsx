import { Button } from '@/components/Button';
import { useAuth } from '@/features/auth';
import { SettingsRow, SettingsSection } from './SettingsSection';

/**
 * Sign this computer out. The rail has the same button on desktop; on phone this row is the only
 * way out (hand-entered tokens never appear under "Signed-in computers"). Keep it last.
 */
export function SignOutSection() {
  const { signOut } = useAuth();
  return (
    <SettingsSection title="This computer" card>
      <SettingsRow
        icon="logout"
        headline="Signed in"
        supporting="Sign out to forget the token on this computer."
        trailing={
          <Button variant="danger" size="sm" onClick={() => void signOut()}>
            Sign out
          </Button>
        }
      />
    </SettingsSection>
  );
}
