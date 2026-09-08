import { useMemo } from 'react';
import { qrModel } from '@/lib/qr';
import { cn } from '@/lib/cn';

export interface QrCardProps {
  /** The text to encode. */
  payload: string;
  /** Rendered size in px (the old modal used 232). */
  size?: number;
  label: string;
  className?: string;
}

/**
 * A QR code on a white card, black modules with a 4-module quiet zone, drawn with the same
 * encoder (toqr, EC level M) the vanilla dashboard embedded, so phones scan identical codes.
 * Renders only while mounted: unmount it to take the code out of the DOM.
 */
export function QrCard({ payload, size = 232, label, className }: QrCardProps) {
  const model = useMemo(() => {
    try {
      return qrModel(payload);
    } catch {
      return null;
    }
  }, [payload]);
  if (!model) {
    return (
      <div className={cn('text-body-m text-error', className)} role="alert">
        Could not generate the QR code.
      </div>
    );
  }
  const n = model.size + 2 * model.quiet;
  return (
    <div className={cn('mx-auto w-fit rounded-lg bg-white p-2 shadow-e1', className)}>
      <svg
        viewBox={`${-model.quiet} ${-model.quiet} ${n} ${n}`}
        width={size}
        height={size}
        shapeRendering="crispEdges"
        role="img"
        aria-label={label}
        className="block"
      >
        <rect x={-model.quiet} y={-model.quiet} width={n} height={n} fill="#ffffff" />
        <path d={model.path} fill="#000000" />
      </svg>
    </div>
  );
}
