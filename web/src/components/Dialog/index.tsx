import { useEffect, useId, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Button } from '@/components/Button';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children?: ReactNode;
  /** Buttons row. Put the safe action left, the primary/destructive one right. */
  actions?: ReactNode;
  /** Width class; default 400 px card. */
  className?: string;
  /** Element to focus when opened (defaults to the first button in `actions`). */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

/**
 * M3 dialog on the native <dialog> element (focus trap, Escape, inert background for free).
 * 28 px corners, surface-container-high. Closing via Escape or the backdrop calls onClose.
 */
export function Dialog({ open, onClose, title, children, actions, className, initialFocusRef }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
      const target =
        initialFocusRef?.current ??
        el.querySelector<HTMLElement>('[data-dialog-actions] button:last-of-type');
      target?.focus();
    } else if (!open && el.open) el.close();
  }, [open, initialFocusRef]);

  if (!open) return null;
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // backdrop
      }}
      className={cn(
        'm-auto w-[400px] max-w-[calc(100vw-32px)] rounded-2xl bg-surface-container-high p-6 text-on-surface shadow-e3 outline-none',
        'backdrop:bg-scrim',
        className,
      )}
    >
      <h2 id={titleId} className="m-0 mb-3 text-title-l font-display">
        {title}
      </h2>
      {children && <div className="text-body-m text-on-surface-body [&_p]:m-0 [&_p+p]:mt-2">{children}</div>}
      {actions && (
        <div data-dialog-actions className="mt-6 flex justify-end gap-2">
          {actions}
        </div>
      )}
    </dialog>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: ReactNode;
  children?: ReactNode;
  /** Label of the confirming button. */
  ok?: string;
  cancel?: string;
  /** Destructive: the confirming button is red (filled danger). */
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Confirm/cancel dialog. Destructive confirmations use the danger variant and sit right. */
export function ConfirmDialog({
  open,
  title,
  children,
  ok = 'OK',
  cancel = 'Cancel',
  danger,
  busy,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      actions={
        <>
          <Button variant="text" onClick={onCancel} disabled={busy}>
            {cancel}
          </Button>
          <Button
            variant={danger ? 'filled' : 'filled'}
            className={danger ? 'bg-error text-on-error' : undefined}
            onClick={onConfirm}
            loading={busy}
          >
            {ok}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
