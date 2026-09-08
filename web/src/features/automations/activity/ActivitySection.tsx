import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { IconButton } from '@/components/IconButton';
import { Skeleton } from '@/components/Skeleton';
import { errorMessage, useRoutingLog } from '@/api';
import { cn } from '@/lib/cn';
import { fmtDayHeader } from '@/lib/format';
import { SectionHeader } from '../SectionHeader';
import { ActivityCard } from './ActivityCard';
import { groupRuns, type RunGroup } from './groupRuns';

/** Cards under day headings: Today, Yesterday, Sun, Sep 6 … (by when the newest run happened). */
export function groupsByDay(groups: RunGroup[], now = new Date()): { day: string; groups: RunGroup[] }[] {
  const days: { day: string; groups: RunGroup[] }[] = [];
  for (const g of groups) {
    const day = fmtDayHeader(g.runs[0].created_at, now) || 'Earlier';
    const last = days[days.length - 1];
    if (last && last.day === day) last.groups.push(g);
    else days.push({ day, groups: [g] });
  }
  return days;
}

/**
 * The activity log: recent runs, newest first, under day headings, one card per recording
 * (repeat runs grouped). Polls every 15 s through `useRoutingLog`; the Refresh button fetches now.
 */
export function ActivitySection() {
  const log = useRoutingLog(50);
  const navigate = useNavigate();
  const days = useMemo(() => groupsByDay(groupRuns(log.data?.runs ?? [])), [log.data]);

  return (
    <section aria-labelledby="activity-title">
      <SectionHeader
        title="Activity"
        id="activity-title"
        actions={
          <IconButton
            icon="refresh"
            label="Refresh"
            onClick={() => void log.refetch()}
            disabled={log.isFetching}
            className={cn(log.isFetching && '[&>svg]:animate-spin')}
          />
        }
      />
      {log.isPending ? (
        <div aria-busy="true" aria-label="Loading activity" className="flex flex-col gap-2.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-lg bg-card px-5 py-4 max-md:px-4">
              <Skeleton width="55%" height={16} />
              <Skeleton width="35%" height={12} className="mt-2.5" />
              <Skeleton width="85%" height={14} className="mt-4" />
            </div>
          ))}
        </div>
      ) : log.isError ? (
        <EmptyState
          compact
          icon="error"
          headline="Couldn’t load the activity"
          description={errorMessage(log.error, 'Try again in a moment.')}
          action={
            <Button variant="tonal" icon="refresh" onClick={() => void log.refetch()}>
              Try again
            </Button>
          }
        />
      ) : days.length === 0 ? (
        <EmptyState
          compact
          icon="history"
          headline="Nothing has run yet"
          description="When a transcript is checked against your rules, it shows up here."
        />
      ) : (
        days.map(({ day, groups }) => (
          <section key={day} aria-label={day} className="[&+&]:mt-3">
            <h3 className="m-0 mb-2 px-1 text-title-s text-on-surface-variant">{day}</h3>
            <div role="list" aria-label={`Activity ${day}`}>
              {groups.map((g) => (
                <ActivityCard
                  key={g.runs[0].id}
                  group={g}
                  onOpen={(id) => navigate(`/rec/${encodeURIComponent(id)}`)}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </section>
  );
}
