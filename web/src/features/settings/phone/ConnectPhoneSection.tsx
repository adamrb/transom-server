import { useState } from 'react';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Dialog } from '@/components/Dialog';
import { IconButton } from '@/components/IconButton';
import { tokenStore } from '@/api/token';
import { useIsDesktop } from '@/lib/breakpoints';
import { SettingsRow, SettingsSection } from '../SettingsSection';
import { CopyField } from '@/components/CopyField';
import { QrCard } from './QrCard';
import { connectPayload, loginLink } from './connectPayload';

export interface ConnectPhoneDialogProps {
  open: boolean;
  onClose: () => void;
  /** Defaults to the stored token and this page's origin. */
  token?: string;
  origin?: string;
}

/**
 * The QR the Android app scans to link itself to this server, plus the same details as text:
 * server address, access token (masked) and a sign-in link. The QR leaves the DOM when the dialog
 * closes (Dialog unmounts its children).
 */
export function ConnectPhoneDialog({ open, onClose, token, origin }: ConnectPhoneDialogProps) {
  const t = token ?? tokenStore.get() ?? '';
  const o = origin ?? window.location.origin;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Connect a phone"
      size="md"
      actions={<Button onClick={onClose}>Done</Button>}
    >
      <p>Scan this code with the Plaud Bridge app to link it to this server.</p>
      <div className="mt-4 flex flex-col gap-4">
        <QrCard payload={connectPayload(o, t)} label="Connection QR code" />
        <CopyField label="Server address" value={o} copiedMessage="Server address copied" />
        <CopyField label="Access token" value={t} secret copiedMessage="Access token copied" />
        <CopyField
          label="Sign-in link (opens the dashboard already signed in)"
          value={loginLink(o, t)}
          copiedMessage="Sign-in link copied"
        />
        <Banner tone="warning">
          The QR code, token, and sign-in link all grant full access. Don't screenshot or share them.
        </Banner>
      </div>
    </Dialog>
  );
}

/** Phone: one row with the button that opens the connect dialog. */
export function ConnectPhoneSection() {
  const [open, setOpen] = useState(false);
  const desktop = useIsDesktop();
  return (
    <SettingsSection title="Phone" card>
      <SettingsRow
        icon="qr_code"
        headline="Connect a phone"
        supporting="Link the Plaud Bridge app on a phone to this server."
        trailing={
          // On phone a labelled button would squeeze the row's text; the icon button carries the name.
          desktop ? (
            <Button variant="tonal" icon="qr_code" onClick={() => setOpen(true)}>
              Connect a phone
            </Button>
          ) : (
            <IconButton
              variant="tonal"
              icon="qr_code"
              label="Connect a phone"
              onClick={() => setOpen(true)}
            />
          )
        }
      />
      <ConnectPhoneDialog open={open} onClose={() => setOpen(false)} />
    </SettingsSection>
  );
}
