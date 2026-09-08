import type { RefObject } from 'react';
import { MenuItem, MenuSeparator, Popover } from '@/components';

export type RecordingAction = 'copy' | 'export' | 'download' | 'rename' | 'retranscribe' | 'delete';

export interface MoreMenuProps {
  open: boolean;
  onClose: () => void;
  anchorRef?: RefObject<HTMLElement | null>;
  /** Copy / Export need a transcript with text. */
  hasText: boolean;
  onAction: (action: RecordingAction) => void;
}

/**
 * The recording's overflow menu (a menu on desktop, a sheet on phone): Copy transcript, Export
 * markdown, Download audio, Rename, then the two that change things, Delete last and red.
 */
export function MoreMenu({ open, onClose, anchorRef, hasText, onAction }: MoreMenuProps) {
  const act = (a: RecordingAction) => () => {
    onClose();
    onAction(a);
  };
  return (
    <Popover open={open} onClose={onClose} anchorRef={anchorRef} label="More actions">
      {hasText && (
        <MenuItem icon="content_copy" onClick={act('copy')}>
          Copy transcript
        </MenuItem>
      )}
      {hasText && (
        <MenuItem icon="ios_share" onClick={act('export')}>
          Export markdown
        </MenuItem>
      )}
      <MenuItem icon="download" onClick={act('download')}>
        Download audio
      </MenuItem>
      <MenuItem icon="edit" onClick={act('rename')}>
        Rename
      </MenuItem>
      <MenuSeparator />
      <MenuItem icon="refresh" onClick={act('retranscribe')}>
        Transcribe again…
      </MenuItem>
      <MenuItem icon="delete" danger onClick={act('delete')}>
        Delete…
      </MenuItem>
    </Popover>
  );
}
