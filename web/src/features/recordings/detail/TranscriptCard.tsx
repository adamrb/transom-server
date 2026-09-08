import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, SkeletonText } from '@/components';
import type { Recording, Transcript } from '@/api';
import { countMatches, paragraphsOf, speakerTones, transcriptHasText } from '../lib/transcript';
import { useNowPlayingIndex, usePlayerStore } from '../player/usePlayer';
import { FindInTranscript } from './FindInTranscript';
import { TranscriptParagraph } from './TranscriptParagraph';

export interface TranscriptCardProps {
  rec: Recording;
  transcript: Transcript | null | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  /** Paragraph to flash after a jump (index), or -1. */
  flashIndex: number;
  onRenameSpeaker: (name: string) => void;
}

/**
 * The transcript as a reader: speaker turns, speaker pills on change (click to rename), bookmark
 * bars, the now-playing marker, hover-to-play times, and find-in-transcript with Enter / Shift+Enter.
 */
export function TranscriptCard({
  rec,
  transcript,
  loading,
  error,
  onRetry,
  flashIndex,
  onRenameSpeaker,
}: TranscriptCardProps) {
  const store = usePlayerStore();
  const paras = useMemo(() => paragraphsOf(transcript), [transcript]);
  const starts = useMemo(() => paras.map((p) => Number(p.start) || 0), [paras]);
  const tones = useMemo(
    () => (transcript ? speakerTones(transcript) : new Map<string, number>()),
    [transcript],
  );
  const nowIndex = useNowPlayingIndex(rec.id, starts);

  const [find, setFind] = useState('');
  const [current, setCurrent] = useState(-1);
  const counts = useMemo(() => paras.map((p) => countMatches(p.text, find)), [paras, find]);
  const total = useMemo(() => counts.reduce((a, b) => a + b, 0), [counts]);
  const onFindChange = useCallback((term: string) => {
    setFind(term);
    setCurrent(-1);
  }, []);
  useEffect(() => {
    // A new term lands on its first hit (the old dashboard did the same).
    if (find && total && current < 0) setCurrent(0);
  }, [find, total, current]);
  const step = (dir: 1 | -1) => {
    if (!total) return;
    setCurrent((c) => (c + dir + total) % total);
  };
  // Which paragraph holds the current hit, and the hit's index within it.
  const [curPara, curLocal] = useMemo(() => {
    if (current < 0) return [-1, -1];
    let k = current;
    for (let i = 0; i < counts.length; i++) {
      if (k < counts[i]) return [i, k];
      k -= counts[i];
    }
    return [-1, -1];
  }, [counts, current]);
  useEffect(() => {
    if (curPara < 0) return;
    const el = document.getElementById(`para-${curPara}`)?.querySelector('mark[data-current]');
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [curPara, curLocal]);

  const seek = useCallback((s: number) => void store.seek(s), [store]);
  const speakerCount = transcript?.speakers.length ?? 0;

  let body: React.ReactNode;
  if (transcript && !transcriptHasText(transcript)) {
    body = <p className="m-0 text-body-m text-on-surface-variant">No speech was found in this recording.</p>;
  } else if (transcript) {
    let prev: string | null = null;
    body = (
      <div data-transcript className="-mx-3.5 md:-mx-2">
        {paras.map((p, i) => {
          const showSpeaker = !!p.speaker && p.speaker !== prev;
          if (p.speaker) prev = p.speaker;
          return (
            <TranscriptParagraph
              key={i}
              index={i}
              paragraph={p}
              showSpeaker={showSpeaker}
              tone={tones.get(p.speaker ?? '') ?? 1}
              now={i === nowIndex}
              flash={i === flashIndex}
              find={find}
              currentMatch={i === curPara ? curLocal : -1}
              onSeek={seek}
              onRenameSpeaker={onRenameSpeaker}
            />
          );
        })}
        {!paras.length && (
          <p className="m-0 px-3.5 whitespace-pre-wrap text-transcript text-on-surface-body">
            {transcript.text}
          </p>
        )}
      </div>
    );
  } else if (rec.status === 'stored') {
    body = (
      <p className="m-0 text-body-m text-on-surface-variant">
        This recording was stored without a transcript.
      </p>
    );
  } else if (loading) {
    body = <SkeletonText lines={4} />;
  } else if (error) {
    body = (
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-body-m text-error">Couldn't load the transcript.</span>
        <Button variant="outlined" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  } else return null;

  return (
    <Card
      id="sec-transcript"
      title={
        <>
          Transcript
          {speakerCount > 1 && (
            <span className="ml-2 text-body-s font-normal text-on-surface-variant max-md:hidden">
              click a name to rename
            </span>
          )}
        </>
      }
      actions={
        transcript && transcriptHasText(transcript) ? (
          <FindInTranscript onChange={onFindChange} onStep={step} total={total} current={current} />
        ) : undefined
      }
      className="[&>div:first-child]:flex-wrap"
    >
      {body}
    </Card>
  );
}
