import { useEffect, useId, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { useIsDesktop } from '@/lib/breakpoints';
import { IconButton } from '@/components/IconButton';

export interface EditorDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Buttons: safe action first, primary last. On phone they move into the top bar. */
  actions: ReactNode;
  /** Focus target on open (defaults to the first text field). */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

/**
 * The rule editor's frame: a 560 px dialog with a scrolling body on desktop, an M3 full-screen
 * dialog on phone (close glyph, title and the primary action in a top bar, body scrolls).
 * Built on the native <dialog> like the design system's Dialog; that one is fixed at 400 px
 * and has no full-screen form, so this wraps the same behaviour locally.
 */
export function EditorDialog({
  open,
  onClose,
  title,
  children,
  actions,
  initialFocusRef,
}: EditorDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const desktop = useIsDesktop();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
      const target =
        initialFocusRef?.current ?? el.querySelector<HTMLElement>('input:not([type=radio]), textarea');
      target?.focus();
    } else if (!open && el.open) el.close();
  }, [open, initialFocusRef]);

  if (!open) return null;
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      data-presentation={desktop ? 'dialog' : 'fullscreen'}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // backdrop
      }}
      className={cn(
        'flex-col bg-surface-container-high p-0 text-on-surface outline-none open:flex [--field-bg:var(--sc-high)]',
        'backdrop:bg-scrim',
        desktop
          ? 'm-auto max-h-[calc(100vh-64px)] w-[560px] max-w-[calc(100vw-32px)] rounded-2xl shadow-e3'
          : 'inset-0 m-0 h-full max-h-none w-full max-w-none rounded-none',
      )}
    >
      {desktop ? (
        <h2 id={titleId} className="m-0 px-6 pt-6 pb-2 font-display text-title-l">
          {title}
        </h2>
      ) : (
        <div className="flex h-16 shrink-0 items-center gap-2 pr-3 pl-1">
          <IconButton icon="close" label="Close" onClick={onClose} />
          <h2 id={titleId} className="m-0 min-w-0 flex-1 truncate font-display text-title-l">
            {title}
          </h2>
          <div data-dialog-actions className="flex items-center gap-1">
            {actions}
          </div>
        </div>
      )}
      <div
        className={cn(
          'min-h-0 flex-1 overflow-y-auto text-body-m text-on-surface-body',
          desktop ? 'px-6 py-2' : 'px-4 pt-2 pb-8',
        )}
      >
        {children}
      </div>
      {desktop && (
        <div data-dialog-actions className="flex shrink-0 justify-end gap-2 px-6 pt-4 pb-6">
          {actions}
        </div>
      )}
    </dialog>
  );
}
