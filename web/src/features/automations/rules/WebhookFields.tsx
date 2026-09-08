import { useState } from 'react';
import { Chip } from '@/components/Chip';
import { IconButton } from '@/components/IconButton';
import { TextField } from '@/components/TextField';

export interface WebhookFieldsProps {
  url: string;
  onUrl: (v: string) => void;
  /** What the user typed for the secret header this session; blank keeps the saved one. */
  secret: string;
  onSecret: (v: string) => void;
  /** The rule already has a secret header on the server (its value never comes back). */
  hasSavedSecret: boolean;
  /** Drop the saved header on save (only offered when one is saved). */
  clearSecret: boolean;
  onClearSecret: (v: boolean) => void;
  errors?: { url?: string; secret?: string };
  disabled?: boolean;
}

/**
 * Agent address plus the optional secret header. The header is a password field with Show/Hide;
 * when the rule already has one the field is blank with the placeholder "Set. Leave blank to keep
 * it." and a chip offers to remove it, because the server rebuilds the whole action on save.
 */
export function WebhookFields({
  url,
  onUrl,
  secret,
  onSecret,
  hasSavedSecret,
  clearSecret,
  onClearSecret,
  errors,
  disabled,
}: WebhookFieldsProps) {
  const [show, setShow] = useState(false);
  const secretDisabled = disabled || clearSecret;
  return (
    <div className="flex flex-col gap-4">
      <TextField
        label="Agent address"
        type="url"
        inputMode="url"
        autoComplete="off"
        spellCheck={false}
        placeholder="https://example.com/hook"
        value={url}
        onChange={(e) => onUrl(e.target.value)}
        error={!!errors?.url}
        helper={errors?.url}
        disabled={disabled}
      />
      <TextField
        label="Secret header (optional)"
        type={show ? 'text' : 'password'}
        autoComplete="off"
        spellCheck={false}
        placeholder={hasSavedSecret ? 'Set. Leave blank to keep it.' : 'Authorization: Bearer …'}
        value={secret}
        onChange={(e) => onSecret(e.target.value)}
        error={!!errors?.secret}
        helper={
          errors?.secret ??
          (clearSecret
            ? 'The saved header is removed when you save.'
            : 'Sent with every hand-off so the agent knows it is you. Written as Name: value.')
        }
        disabled={secretDisabled}
        trailing={
          <IconButton
            icon={show ? 'visibility_off' : 'visibility'}
            label={show ? 'Hide the secret header' : 'Show the secret header'}
            onClick={() => setShow((s) => !s)}
            disabled={secretDisabled}
            className="-mr-2"
          />
        }
      />
      {hasSavedSecret && (
        <div className="-mt-1">
          <Chip
            variant="filter"
            icon="delete"
            selected={clearSecret}
            onClick={() => onClearSecret(!clearSecret)}
            disabled={disabled}
          >
            Remove the saved secret header
          </Chip>
        </div>
      )}
    </div>
  );
}
