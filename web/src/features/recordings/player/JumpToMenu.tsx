import type { RefObject } from 'react';
import { Icon, MenuItem, MenuLabel, MenuSeparator, Popover } from '@/components';
import type { JumpItem, JumpSection } from '../lib/jump';

export interface JumpToMenuProps {
  open: boolean;
  onClose: () => void;
  anchorRef?: RefObject<HTMLElement | null>;
  sections: JumpSection[];
  onSelect: (item: JumpItem) => void;
}

/**
 * The "Jump to" popover: a menu on desktop, a bottom sheet on phone. Back to top, then the
 * bookmarks (amber, with a star), speaker changes and the 10-minute marks, each with its time.
 */
export function JumpToMenu({ open, onClose, anchorRef, sections, onSelect }: JumpToMenuProps) {
  return (
    <Popover
      open={open}
      onClose={onClose}
      anchorRef={anchorRef}
      title="Jump to"
      label="Jump to"
      className="max-md:max-h-[78vh]"
    >
      {sections.map((s, si) => (
        <div key={si}>
          {si > 0 && <MenuSeparator />}
          {s.label && <MenuLabel>{s.label}</MenuLabel>}
          {s.items.map((item, i) => (
            <MenuItem
              key={i}
              time={'time' in item ? item.time : undefined}
              icon={item.kind === 'top' ? 'keyboard_arrow_up' : undefined}
              className={item.kind === 'bookmark' ? 'text-warning' : undefined}
              onClick={() => {
                onClose();
                onSelect(item);
              }}
            >
              {item.kind === 'bookmark' ? (
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="star_fill" size={16} />
                  {item.label}
                </span>
              ) : (
                item.label
              )}
            </MenuItem>
          ))}
        </div>
      ))}
    </Popover>
  );
}
