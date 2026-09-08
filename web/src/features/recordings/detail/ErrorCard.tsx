import { Card } from '@/components';
import type { Recording } from '@/api';
import { Disclosure } from './Disclosure';

/** A failed recording: the server's sentence for people; the raw detail only behind a disclosure. */
export function ErrorCard({ rec }: { rec: Pick<Recording, 'error' | 'error_detail'> }) {
  if (!rec.error) return null;
  return (
    <Card title="Something went wrong" role="alert">
      <p className="m-0 text-body-m text-error">{rec.error}</p>
      {rec.error_detail && <Disclosure>{rec.error_detail}</Disclosure>}
    </Card>
  );
}
