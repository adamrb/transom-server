import type { ReactNode } from 'react';
import { Popover } from '@/components';
import { Player } from './Player';
import { usePlayerSelector } from './usePlayer';

export interface PlayerSheetProps {
  open: boolean;
  onClose: () => void;
  /** Under the title: the recording's date line. */
  subtitle?: ReactNode;
  trailing?: ReactNode;
}

/** Phone: the full player in a bottom sheet, opened from the mini player. */
export function PlayerSheet({ open, onClose, subtitle, trailing }: PlayerSheetProps) {
  const title = usePlayerSelector((s) => s.title);
  return (
    <Popover open={open} onClose={onClose} as="sheet" label="Player">
      <div className="px-2 pt-2">
        <div className="mb-0.5 truncate text-title-m text-on-surface">{title}</div>
        {subtitle && <div className="mb-3 text-body-s text-on-surface-variant">{subtitle}</div>}
      </div>
      <Player variant="sheet" trailing={trailing} />
    </Popover>
  );
}
