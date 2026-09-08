import { forwardRef, memo, type MouseEvent } from 'react';
import { Avatar, IconButton, ListItem, StatusChip, type AvatarKind } from '@/components';
import { isInFlight, type Recording } from '@/api';
import { cn } from '@/lib/cn';
import { fmtDuration, fmtTime, parseDate } from '@/lib/format';
import { Highlighted } from '../lib/Highlighted';
import { titleOf } from '../lib/summary';
import { inFlightReason, statusWord } from '../lib/status';

export interface RecordingRowProps {
  rec: Recording;
  /** The search term, to mark in the snippet. */
  q: string;
  selected: boolean;
  onOpen: (id: string) => void;
  /** Phone: the ⋮ button. Omit on desktop. */
  onMore?: (rec: Recording, anchor: HTMLElement) => void;
  className?: string;
}

/** The preview is the transcript's first line; the engine's speaker label adds nothing in a list row. */
export function stripSpeakerLabel(preview: string): string {
  return preview.replace(/^(Speaker \d+|Unknown speaker):\s+/, '');
}

function avatarKind(rec: Recording): AvatarKind {
  if (rec.status === 'failed') return 'failed';
  if (rec.status === 'pending') return 'waiting';
  if (rec.status === 'transcribing')
    return typeof rec.progress === 'number' && rec.stage === 'transcribing' ? 'progress' : 'waiting';
  if (rec.no_speech) return 'silent';
  return 'waveform';
}

/**
 * One recording in the list: avatar, title, a supporting line (status word and reason while in
 * flight; time · duration · preview otherwise), and on the right the time (with a status word) or
 * the bookmark count. Memoised: polling only re-renders rows whose data changed.
 */
export const RecordingRow = memo(
  forwardRef<HTMLDivElement, RecordingRowProps>(function RecordingRow(
    { rec, q, selected, onOpen, onMore, className },
    ref,
  ) {
    const word = statusWord(rec);
    const d = parseDate(rec.started_at || rec.uploaded_at);
    const time = d ? fmtTime(d) : '';
    const dur = rec.duration_s ? fmtDuration(rec.duration_s) : '';
    const when = [time, dur].filter(Boolean).join(' · ');
    const snippet = rec.match_snippet && rec.match_field !== 'title';
    const preview = stripSpeakerLabel(snippet ? rec.match_snippet! : rec.text_preview || '');
    const marks = rec.marks?.length ?? 0;

    let supporting: React.ReactNode;
    if (word && isInFlight(rec)) {
      supporting = (
        <>
          <StatusChip tone={word.tone}>{word.label}</StatusChip>
          <span className="truncate">{inFlightReason(rec).replace(/\.$/, '')}</span>
        </>
      );
    } else if (word) {
      // Failed / No speech / Not transcribed: the word, the length; the time sits on the right.
      supporting = (
        <>
          <StatusChip tone={word.tone}>{word.label}</StatusChip>
          {dur && <span className="truncate tnum">{dur}</span>}
        </>
      );
    } else {
      supporting = (
        <span className="truncate">
          <span className="tnum">{when}</span>
          {preview && (
            <span className="opacity-85">
              {when ? ' · ' : ''}
              {snippet && rec.match_field === 'summary' && <i>Summary: </i>}
              {snippet ? <Highlighted text={preview} term={q} /> : preview}
            </span>
          )}
        </span>
      );
    }

    const star = marks > 0 && (
      <StatusChip
        tone="star"
        icon="star_fill"
        title={`${marks} highlight${marks > 1 ? 's' : ''} marked on the recorder`}
      >
        {marks}
      </StatusChip>
    );
    const trailing = onMore ? (
      <div className="flex items-center gap-1">
        {star}
        <IconButton
          icon="more_vert"
          label="More"
          onClick={(e: MouseEvent<HTMLButtonElement>) => {
            e.stopPropagation();
            onMore(rec, e.currentTarget);
          }}
          onKeyDown={(e) => e.stopPropagation()}
        />
      </div>
    ) : word ? (
      time && <span className="tnum">{time}</span>
    ) : (
      star
    );

    return (
      <ListItem
        ref={ref}
        data-row={rec.id}
        aria-current={selected || undefined}
        leading={<Avatar kind={avatarKind(rec)} value={rec.progress} selected={selected} />}
        headline={titleOf(rec)}
        supporting={supporting}
        trailing={trailing || undefined}
        selected={selected}
        interactive
        onClick={() => onOpen(rec.id)}
        className={cn('mb-1.5', className)}
      />
    );
  }),
);
