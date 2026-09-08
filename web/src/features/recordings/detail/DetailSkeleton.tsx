import { Card, Skeleton, SkeletonText } from '@/components';

/** The detail body while the recording loads: title, meta line and one card of text lines. */
export function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading recording" className="pt-6">
      <Skeleton width="60%" height={28} className="my-2 mb-3" />
      <Skeleton width="30%" height={14} className="mb-6" />
      <Card>
        <SkeletonText lines={3} />
      </Card>
    </div>
  );
}
