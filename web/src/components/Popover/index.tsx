import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/cn';
import { useIsDesktop } from '@/lib/breakpoints';
import { Icon, type IconName } from '@/components/Icon';

export interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** The button that opened it; the desktop menu is positioned against it. */
  anchorRef?: RefObject<HTMLElement | null>;
  /** Sheet heading on phone (title-l). Menus have none. */
  title?: ReactNode;
  /** Force one presentation regardless of width (the player sheet is always a sheet). */
  as?: 'auto' | 'menu' | 'sheet';
  /** Menu alignment against the anchor. */
  align?: 'end' | 'start';
  /** Desktop menu at least as wide as the anchor (selects). */
  matchAnchorWidth?: boolean;
  /** `menu` holds `MenuItem`s; `listbox` holds options (`MenuItem role="option" selected`). */
  role?: 'menu' | 'listbox';
  /** Accessible name for the menu / dialog. */
  label?: string;
  /** Id of the menu / listbox element (for a combobox's aria-controls). */
  id?: string;
  /**
   * Where to portal. Defaults to the nearest open `<dialog>` around the anchor (so a menu inside
   * a modal dialog stays in its top layer and interactive), else document.body.
   */
  container?: HTMLElement | null;
  children: ReactNode;
  className?: string;
}

const ITEM_SELECTOR = '[role=menuitem]:not([disabled]),[role=option]:not([disabled])';

/**
 * One popover that renders as an M3 menu (desktop, ≥ 840 px: elevation 2, 4 px corners, scales in
 * from the anchor) or a bottom sheet (phone: 28 px top corners, scrim, slides up). Escape and a
 * click outside close it; arrow keys move between items; focus goes to the selected item, else
 * the first.
 */
export function Popover({
  open,
  onClose,
  anchorRef,
  title,
  as = 'auto',
  align = 'end',
  matchAnchorWidth,
  role = 'menu',
  label,
  id,
  container,
  children,
  className,
}: PopoverProps) {
  const desktop = useIsDesktop();
  const asSheet = as === 'sheet' || (as === 'auto' && !desktop);
  const panel = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{
    top: number;
    left?: number;
    right?: number;
    minWidth?: number;
    maxHeight: number;
  } | null>(null);
  const [shown, setShown] = useState(false); // one frame later, for the enter transition

  useLayoutEffect(() => {
    if (!open || asSheet) return;
    const a = anchorRef?.current;
    const r = a
      ? a.getBoundingClientRect()
      : { top: 48, bottom: 72, left: 24, right: window.innerWidth - 24, width: 0 };
    const h = panel.current?.offsetHeight ?? 320;
    let top = r.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
    const maxHeight = Math.min(window.innerHeight * 0.7, window.innerHeight - top - 8);
    const minWidth = matchAnchorWidth && a ? r.width : undefined;
    setPos(
      align === 'end'
        ? { top, right: Math.max(8, window.innerWidth - r.right), maxHeight, minWidth }
        : { top, left: Math.max(8, r.left), maxHeight, minWidth },
    );
  }, [open, asSheet, anchorRef, align, matchAnchorWidth]);

  useEffect(() => {
    if (!open) {
      setShown(false);
      return;
    }
    const raf = requestAnimationFrame(() => setShown(true));
    const selected = panel.current?.querySelector<HTMLElement>('[role=option][aria-selected=true]');
    const first = selected ?? panel.current?.querySelector<HTMLElement>(ITEM_SELECTOR);
    (first ?? panel.current)?.focus({ preventScroll: true });
    const onDoc = (e: MouseEvent) => {
      if (
        panel.current &&
        !panel.current.contains(e.target as Node) &&
        !anchorRef?.current?.contains(e.target as Node)
      )
        onClose();
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Stop a surrounding <dialog> from closing on the same key press.
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose, anchorRef]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
    const items = [...(panel.current?.querySelectorAll<HTMLElement>(ITEM_SELECTOR) ?? [])];
    if (!items.length) return;
    e.preventDefault();
    const i = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === 'Home'
        ? items[0]
        : e.key === 'End'
          ? items[items.length - 1]
          : e.key === 'ArrowDown'
            ? items[(i + 1) % items.length]
            : items[(i - 1 + items.length) % items.length];
    next.focus();
  };

  if (!open) return null;
  const target =
    container ??
    (anchorRef?.current?.closest('dialog[open]') as HTMLElement | null | undefined) ??
    document.body;
  const name = label ?? (typeof title === 'string' ? title : undefined);
  const listbox = role === 'listbox';
  return createPortal(
    <>
      <div
        data-scrim
        onClick={onClose}
        className={cn(
          'fixed inset-0 z-40 transition-opacity dur-medium ease-standard',
          asSheet ? 'bg-scrim' : 'bg-transparent',
          shown ? 'opacity-100' : 'opacity-0',
        )}
      />
      <div
        ref={panel}
        id={asSheet && listbox ? undefined : id}
        role={asSheet ? 'dialog' : role}
        aria-modal={asSheet || undefined}
        aria-label={name}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        data-presentation={asSheet ? 'sheet' : 'menu'}
        style={asSheet ? undefined : (pos ?? undefined)}
        className={cn(
          'fixed z-50 outline-none',
          asSheet
            ? cn(
                'inset-x-0 bottom-0 max-h-[78vh] overflow-auto rounded-t-2xl bg-surface-container-low px-4 pb-6 shadow-e3 dark:bg-surface-container-high',
                'transition-transform dur-long ease-emph-decel',
                shown ? 'translate-y-0' : 'translate-y-full',
              )
            : cn(
                'min-w-[220px] overflow-auto rounded-xs bg-surface-container py-2 shadow-e2 dark:bg-surface-container-high',
                'transition-[transform,opacity] dur-short ease-standard',
                align === 'end' ? 'origin-top-right' : 'origin-top-left',
                shown ? 'scale-100 opacity-100' : 'scale-90 opacity-0',
              ),
          className,
        )}
      >
        {asSheet && (
          <>
            <div
              aria-hidden
              className="mx-auto mt-3.5 mb-3 h-1 w-8 rounded-full bg-on-surface-variant opacity-40"
            />
            {title && <h4 className="mx-2 mt-2 mb-3 text-title-l font-display text-on-surface">{title}</h4>}
          </>
        )}
        {listbox && asSheet ? (
          <div id={id} role="listbox" aria-label={name}>
            {children}
          </div>
        ) : (
          children
        )}
      </div>
    </>,
    target,
  );
}

/* ------------------------------------ menu items ------------------------------------ */

export interface MenuItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: IconName;
  /** Red text (Delete…). Keep danger items last, after a separator. */
  danger?: boolean;
  /** Fixed-width leading text such as a time (Jump to). */
  time?: string;
  /** For `role="option"` rows in a listbox: the chosen one gets aria-selected and a check mark. */
  selected?: boolean;
  /** One line under the label (an option's detail). */
  description?: ReactNode;
  children: ReactNode;
}

/** 48 px menu row on desktop, 52 px rounded row in a sheet (styled by the parent presentation). */
export function MenuItem({
  icon,
  danger,
  time,
  selected,
  description,
  className,
  children,
  type = 'button',
  role = 'menuitem',
  ...rest
}: MenuItemProps) {
  return (
    <button
      type={type}
      role={role}
      aria-selected={role === 'option' ? !!selected : undefined}
      className={cn(
        'flex w-full items-center gap-3 whitespace-nowrap px-3 text-body-m text-on-surface hover:bg-state-hover focus-ring',
        'h-12 [[data-presentation=sheet]_&]:h-13 [[data-presentation=sheet]_&]:rounded-md [[data-presentation=sheet]_&]:px-2 [[data-presentation=sheet]_&]:text-body-l [[data-presentation=sheet]_&]:gap-4',
        description && 'h-auto min-h-12 py-2 [[data-presentation=sheet]_&]:h-auto',
        danger && 'text-error',
        selected && 'bg-selection-tint',
        'disabled:opacity-[.38]',
        className,
      )}
      {...rest}
    >
      {time && (
        <span className="w-16 shrink-0 text-[13px] text-on-surface-variant tnum [[data-presentation=sheet]_&]:w-[72px] [[data-presentation=sheet]_&]:text-on-surface [[data-presentation=sheet]_&]:font-medium">
          {time}
        </span>
      )}
      {icon && <Icon name={icon} size={20} className={danger ? 'text-error' : 'text-on-surface-variant'} />}
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate">{children}</span>
        {description && (
          <span className="block truncate text-body-s text-on-surface-variant">{description}</span>
        )}
      </span>
      {selected && <Icon name="check" size={18} className="shrink-0 text-primary" />}
    </button>
  );
}

export function MenuSeparator() {
  return <div role="separator" className="my-2 h-px bg-outline-variant" />;
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-4 pt-2 pb-1 text-label-m text-on-surface-variant [[data-presentation=sheet]_&]:px-2 [[data-presentation=sheet]_&]:pt-3 [[data-presentation=sheet]_&]:text-body-m">
      {children}
    </div>
  );
}
