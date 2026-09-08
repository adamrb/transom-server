import { useEffect, useId, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { useIsDesktop } from '@/lib/breakpoints';
import { Button } from '@/components/Button';
import { IconButton } from '@/components/IconButton';

export type DialogSize = 'sm' | 'md' | 'lg';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children?: ReactNode;
  /** Buttons row. Put the safe action left, the primary/destructive one right. */
  actions?: ReactNode;
  /** sm = 400 px (confirms, rename), md = 560 px (forms), lg = 720 px. */
  size?: DialogSize;
  /**
   * M3 full-screen dialog on phone (< 840 px): fills the screen with a top bar holding a close
   * glyph, the title and `actions`. Desktop keeps the centred card. Put the cancel button in
   * `actions` with `max-md:hidden`, the close glyph replaces it.
   */
  fullScreen?: boolean;
  /** Extra classes on the <dialog> (rarely needed; prefer `size`). */
  className?: string;
  /** Element to focus when opened (defaults to the first button in `actions`). */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

const SIZE: Record<DialogSize, string> = {
  sm: 'w-[400px]',
  md: 'w-[560px]',
  lg: 'w-[720px]',
};

/**
 * M3 dialog on the native <dialog> element (focus trap, Escape, inert background for free).
 * 28 px corners, surface-container-high, the body scrolls when the content is taller than the
 * viewport. Closing via Escape or the backdrop calls onClose.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  actions,
  size = 'sm',
  fullScreen,
  className,
  initialFocusRef,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const desktop = useIsDesktop();
  const fs = !!fullScreen && !desktop;

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
      data-presentation={fs ? 'fullscreen' : 'dialog'}
      data-size={size}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // backdrop
      }}
      className={cn(
        // Floating text-field labels inside need the dialog's colour behind them.
        'flex-col bg-surface-container-high p-0 text-on-surface outline-none open:flex [--field-bg:var(--sc-high)]',
        'backdrop:bg-scrim',
        fs
          ? 'inset-0 m-0 h-full max-h-none w-full max-w-none rounded-none'
          : cn('m-auto max-h-[calc(100vh-64px)] max-w-[calc(100vw-32px)] rounded-2xl shadow-e3', SIZE[size]),
        className,
      )}
    >
      {fs ? (
        <div className="flex h-16 shrink-0 items-center gap-2 pr-3 pl-1">
          <IconButton icon="close" label="Close" onClick={onClose} />
          <h2 id={titleId} className="m-0 min-w-0 flex-1 truncate font-display text-title-l">
            {title}
          </h2>
          {actions && (
            <div data-dialog-actions className="flex items-center gap-1">
              {actions}
            </div>
          )}
        </div>
      ) : (
        <h2 id={titleId} className="m-0 px-6 pt-6 font-display text-title-l">
          {title}
        </h2>
      )}
      {children && (
        <div
          className={cn(
            'min-h-0 flex-1 overflow-y-auto text-body-m text-on-surface-body [&_p]:m-0 [&_p+p]:mt-2',
            fs ? 'px-4 pt-3 pb-8' : 'px-6 pt-3 pb-2',
          )}
        >
          {children}
        </div>
      )}
      {actions && !fs && (
        <div
          data-dialog-actions
          className={cn('flex shrink-0 justify-end gap-2 px-6 pb-6', children ? 'pt-4' : 'pt-6')}
        >
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
  /** Destructive: the confirming button is filled red (error / on-error). */
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
          <Button variant={danger ? 'danger-filled' : 'filled'} onClick={onConfirm} loading={busy}>
            {ok}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
