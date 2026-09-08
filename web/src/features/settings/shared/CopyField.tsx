import { useId, useState } from 'react';
import { IconButton } from '@/components/IconButton';
import { useSnackbar } from '@/components/Snackbar';
import { copyText } from '@/features/shell/bridge';
import { cn } from '@/lib/cn';

export interface CopyFieldProps {
  label: string;
  value: string;
  /** Mask the value (an access token) until the user reveals it. */
  secret?: boolean;
  /** Snackbar text after a successful copy. */
  copiedMessage?: string;
  className?: string;
}

/**
 * A read-only value with a Copy button (server address, token, sign-in link). Secrets start
 * masked with a reveal toggle. Copy goes through the app bridge when embedded, which shows its
 * own toast, so the snackbar only fires for web copies.
 */
export function CopyField({ label, value, secret, copiedMessage = 'Copied', className }: CopyFieldProps) {
  const id = useId();
  const [shown, setShown] = useState(!secret);
  const snackbar = useSnackbar();
  const copy = async () => {
    const r = await copyText(value);
    if (r === 'copied') snackbar.show(copiedMessage);
    else if (r === 'failed') snackbar.error("Couldn't copy. Select the text and copy it by hand.");
  };
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-body-s text-on-surface-variant">
        {label}
      </label>
      <div className="flex items-center gap-1 rounded-md border border-outline pl-3.5 pr-1">
        {/* Masked with dots rather than type=password so password managers leave it alone. */}
        <input
          id={id}
          type="text"
          readOnly
          autoComplete="off"
          data-masked={shown ? undefined : true}
          value={shown ? value : '•'.repeat(Math.min(value.length, 24))}
          onFocus={(e) => e.currentTarget.select()}
          className="h-12 min-w-0 flex-1 bg-transparent font-mono text-mono text-on-surface outline-none"
        />
        {secret && (
          <IconButton
            icon={shown ? 'visibility_off' : 'visibility'}
            label={shown ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            onClick={() => setShown((s) => !s)}
          />
        )}
        <IconButton icon="content_copy" label={`Copy ${label.toLowerCase()}`} onClick={() => void copy()} />
      </div>
    </div>
  );
}
