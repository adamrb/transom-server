import { useEffect, useState } from 'react';
import { TextField } from '@/components';
import { cn } from '@/lib/cn';

export interface FindInTranscriptProps {
  /** Debounced term, as applied to the transcript. */
  onChange: (term: string) => void;
  /** Enter → +1, Shift+Enter → −1. */
  onStep: (step: 1 | -1) => void;
  /** Total hits and the current one (0-based, -1 for none) for the count label. */
  total: number;
  current: number;
  className?: string;
}

/** The find field in the transcript heading, with "3 matches" / "2 of 5" / "No matches" beside it. */
export function FindInTranscript({ onChange, onStep, total, current, className }: FindInTranscriptProps) {
  const [value, setValue] = useState('');
  useEffect(() => {
    const t = setTimeout(() => onChange(value.trim()), 150);
    return () => clearTimeout(t);
  }, [value, onChange]);

  const count = !value.trim()
    ? ''
    : !total
      ? 'No matches'
      : current >= 0
        ? `${current + 1} of ${total}`
        : `${total} match${total === 1 ? '' : 'es'}`;

  return (
    <div className={cn('flex items-center gap-2', className)}>
      {count && (
        <span className="whitespace-nowrap text-body-s text-on-surface-variant tnum" aria-live="polite">
          {count}
        </span>
      )}
      <TextField
        size="sm"
        icon="search"
        placeholder="Find in transcript"
        aria-label="Find in transcript"
        autoComplete="off"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            onStep(e.shiftKey ? -1 : 1);
          }
        }}
        className="w-[220px] max-w-[45vw]"
      />
    </div>
  );
}
