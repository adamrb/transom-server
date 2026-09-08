import { useState } from 'react';
import { ConfirmDialog } from '@/components/Dialog';
import { IconButton } from '@/components/IconButton';
import { Skeleton } from '@/components/Skeleton';
import { useSnackbar } from '@/components/Snackbar';
import { ApiError, errorMessage } from '@/api/client';
import { useRevokeSession, useSessions } from '@/api/hooks/auth';
import type { Session } from '@/api/types';
import { SettingsSection } from '../SettingsSection';
import { SessionRow, sessionLabel } from './SessionRow';

const HAND_TOKENS_NOTE = 'Tokens entered by hand are not listed.';

function Note({ children }: { children: string }) {
  return <p className="m-0 py-3.5 text-body-m text-on-surface-variant">{children}</p>;
}

/**
 * Signed-in computers: every session minted by approving a QR sign-in, with a Sign out that
 * asks first. The list is what the server knows; hand-entered tokens have no session, hence
 * the note. A 404 means an older server without the sessions feature.
 */
export function SessionsSection() {
  const query = useSessions();
  const revoke = useRevokeSession();
  const snackbar = useSnackbar();
  const [target, setTarget] = useState<Session | null>(null);

  const confirmRevoke = () => {
    if (!target) return;
    revoke.mutate(target.id, {
      onSuccess: () => snackbar.show('Signed out'),
      onError: (e) => snackbar.error(errorMessage(e, "Couldn't sign that computer out.")),
      onSettled: () => setTarget(null),
    });
  };

  const sessions = query.data?.sessions ?? [];
  const unsupported = query.error instanceof ApiError && query.error.notFound;

  return (
    <SettingsSection
      title="Signed-in computers"
      card
      actions={
        <IconButton
          icon="refresh"
          label="Refresh signed-in computers"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        />
      }
    >
      {query.isPending ? (
        <div
          className="flex items-center gap-4 py-3.5"
          aria-busy="true"
          aria-label="Loading signed-in computers"
        >
          <Skeleton width={40} height={40} />
          <div className="flex-1">
            <Skeleton width="40%" height={14} className="my-[5px]" />
            <Skeleton width="60%" height={12} className="my-1" />
          </div>
        </div>
      ) : unsupported ? (
        <Note>Your server does not list signed-in computers yet.</Note>
      ) : query.isError && !query.data ? (
        <Note>{errorMessage(query.error, "Couldn't load signed-in computers.")}</Note>
      ) : sessions.length === 0 ? (
        <Note>{`No computers signed in with a QR code. ${HAND_TOKENS_NOTE}`}</Note>
      ) : (
        <>
          {sessions.map((s) => (
            <SessionRow key={s.id} session={s} onRevoke={setTarget} busy={revoke.isPending} />
          ))}
          <p className="m-0 border-t border-outline-variant py-3 text-body-s text-on-surface-variant">
            {HAND_TOKENS_NOTE}
          </p>
        </>
      )}
      <ConfirmDialog
        open={target !== null}
        danger
        title="Sign out this computer?"
        ok="Sign out"
        busy={revoke.isPending}
        onConfirm={confirmRevoke}
        onCancel={() => !revoke.isPending && setTarget(null)}
      >
        {target && (
          <p>
            <b>{sessionLabel(target)}</b> will have to sign in again.
            {target.current ? ' That is this computer: you will land on the sign-in screen.' : ''}
          </p>
        )}
      </ConfirmDialog>
    </SettingsSection>
  );
}
