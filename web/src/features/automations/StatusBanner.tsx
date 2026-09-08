import { Banner } from '@/components/Banner';
import { Skeleton } from '@/components/Skeleton';
import { ApiError, errorMessage, type Route, type RouterStatus } from '@/api';
import { capitalize, fmtWhen, numberWord } from '@/lib/format';

export interface StatusBannerProps {
  status: RouterStatus | undefined;
  error: unknown;
  loading?: boolean;
  /** When known, the banner adds "Two of three rules are turned on". */
  routes?: readonly Pick<Route, 'enabled'>[];
  /** When known, the banner adds "last run Today 2:48 AM". */
  lastRunAt?: string | null;
  className?: string;
}

/** "Two of three rules are turned on", "All three rules are turned on", "Your rule is turned off"… */
export function rulesSummary(routes: readonly Pick<Route, 'enabled'>[]): string {
  const total = routes.length;
  const on = routes.filter((r) => r.enabled).length;
  if (total === 0) return 'No rules yet';
  if (total === 1) return on ? 'Your rule is turned on' : 'Your rule is turned off';
  if (on === total) return `All ${numberWord(total)} rules are turned on`;
  if (on === 0) return `None of your ${numberWord(total)} rules are turned on`;
  return `${capitalize(numberWord(on))} of ${numberWord(total)} rules are turned on`;
}

/**
 * Whether automations run on the server, in user words only (never the model id, never an env
 * var). Success when turned on and set up; a warning otherwise; a warning when the server is too
 * old to have automations at all.
 */
export function StatusBanner({ status, error, loading, routes, lastRunAt, className }: StatusBannerProps) {
  if (loading && !status && !error) {
    return <Skeleton height={52} className={className} aria-busy="true" data-testid="status-skeleton" />;
  }
  if (error) {
    const unsupported = error instanceof ApiError && error.notFound;
    return (
      <Banner tone="warning" className={className}>
        {unsupported ? (
          <>
            <b>Your server doesn’t support automations yet.</b> Update it to use them.
          </>
        ) : (
          errorMessage(error, 'Couldn’t check whether automations are on.')
        )}
      </Banner>
    );
  }
  if (!status) return null;
  if (status.enabled && status.configured) {
    const extra = [routes ? rulesSummary(routes) : null, lastRunAt ? `last run ${fmtWhen(lastRunAt)}` : null]
      .filter(Boolean)
      .join(' · ');
    return (
      <Banner tone="success" className={className}>
        <b>Automations are on.</b> New transcripts are checked against your rules.
        {extra && <span className="block text-body-s opacity-90">{extra}</span>}
      </Banner>
    );
  }
  return (
    <Banner tone="warning" className={className}>
      <b>
        {status.enabled
          ? 'Automations are not set up on the server.'
          : 'Automations are turned off on the server.'}
      </b>{' '}
      Rules are kept but nothing runs.
    </Banner>
  );
}
