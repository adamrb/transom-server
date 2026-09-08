import { Chip } from '@/components';
import type { RecordingFilter } from '@/api';
import { cn } from '@/lib/cn';
import { FILTERS } from './useListState';

export interface FilterChipsProps {
  value: RecordingFilter | '';
  onChange: (value: RecordingFilter | '') => void;
  className?: string;
}

/** One row of filter chips (All ✓, Waiting, …) that scrolls sideways and fades at the edge. */
export function FilterChips({ value, onChange, className }: FilterChipsProps) {
  return (
    <div
      role="group"
      aria-label="Show"
      className={cn(
        '-mx-4 flex gap-2 overflow-x-auto px-4 pt-1 pb-2 scrollbar-none',
        '[mask-image:linear-gradient(90deg,#000_calc(100%-28px),transparent)]',
        className,
      )}
    >
      {FILTERS.map((f) => (
        <Chip
          key={f.key || 'all'}
          variant="filter"
          selected={value === f.key}
          onClick={() => onChange(f.key)}
          className="shrink-0"
        >
          {f.label}
        </Chip>
      ))}
    </div>
  );
}
