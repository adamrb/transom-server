import { cn } from '@/lib/cn';

export interface SpeakerPillProps {
  name: string;
  /** 1..4: the speaker's colour, stable across renames. */
  tone: number;
  /** Click to rename. */
  onClick?: () => void;
  className?: string;
}

const TONE = [
  '',
  'bg-spk1 text-on-spk1',
  'bg-spk2 text-on-spk2',
  'bg-spk3 text-on-spk3',
  'bg-spk4 text-on-spk4',
];
const DOT = [
  '',
  'bg-on-spk1 text-spk1',
  'bg-on-spk2 text-spk2',
  'bg-on-spk3 text-spk3',
  'bg-on-spk4 text-spk4',
];

/** The speaker label shown when the speaker changes: a numbered dot and the name, in the speaker's tone. */
export function SpeakerPill({ name, tone, onClick, className }: SpeakerPillProps) {
  const t = ((tone - 1) % 4) + 1;
  return (
    <button
      type="button"
      title="Rename this speaker"
      aria-label={`Rename speaker ${name}`}
      onClick={onClick}
      data-tone={t}
      className={cn(
        'inline-flex h-6 items-center gap-2 rounded-full pr-2.5 pl-1 text-[13px] font-medium tracking-[.1px] transition-shadow dur-short hover:shadow-e1 focus-ring',
        TONE[t],
        className,
      )}
    >
      <span
        className={cn(
          'inline-grid size-[18px] place-items-center rounded-full text-[10px] font-bold',
          DOT[t],
        )}
      >
        {tone}
      </span>
      {name}
    </button>
  );
}
