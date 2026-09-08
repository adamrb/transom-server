import { Button } from '@/components/Button';
import { StatusChip } from '@/components/Chip';
import type { Session } from '@/api/types';
import { fmtWhen } from '@/lib/format';
import { SettingsRow } from '../SettingsSection';

export interface SessionRowProps {
  session: Session;
  onRevoke: (session: Session) => void;
  busy?: boolean;
}

/** The label to show for a session ("Web browser" when the phone sent none). */
export const sessionLabel = (s: Pick<Session, 'label'>) => s.label || 'Web browser';

/** One signed-in computer: label, "this computer" badge, when it signed in and was last used. */
export function SessionRow({ session, onRevoke, busy }: SessionRowProps) {
  const supporting = [
    `Signed in ${fmtWhen(session.created_at)}`,
    session.last_used_at ? `last used ${fmtWhen(session.last_used_at)}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <SettingsRow
      icon="computer"
      headline={
        <span className="inline-flex max-w-full items-center gap-2">
          <span className="truncate">{sessionLabel(session)}</span>
          {session.current && <StatusChip tone="ok">this computer</StatusChip>}
        </span>
      }
      supporting={supporting}
      trailing={
        <Button variant="danger" size="sm" disabled={busy} onClick={() => onRevoke(session)}>
          Sign out
        </Button>
      }
    />
  );
}
