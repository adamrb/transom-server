import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ListItem } from '@/components/ListItem';
import { useAuth } from '@/features/auth';

/**
 * Sign this computer out. The rail has the same button on desktop; on phone this row is the only
 * way out (hand-entered tokens never appear under "Signed-in computers"). Keep it last.
 */
export function SignOutSection() {
  const { signOut } = useAuth();
  return (
    <>
      <div className="mt-7 mb-3 flex items-center gap-3">
        <h2 className="m-0 flex-1 font-display text-title-l text-on-surface">This computer</h2>
      </div>
      <Card padding="tight">
        <ListItem
          shape="flat"
          leading={<Avatar kind="icon" icon="logout" size={40} shape="rounded" />}
          headline="Signed in"
          supporting="Sign out to forget the token on this computer."
          trailing={
            <Button variant="danger" size="sm" onClick={() => void signOut()}>
              Sign out
            </Button>
          }
        />
      </Card>
    </>
  );
}
