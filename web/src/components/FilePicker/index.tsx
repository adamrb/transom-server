import { useId, useRef, type ReactNode } from 'react';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';

export interface FilePickerProps {
  label: string;
  /** `accept` attribute (".apk", ".txt,.md"). */
  accept?: string;
  file: File | null;
  onChange: (file: File | null) => void;
  helper?: ReactNode;
  error?: boolean;
  disabled?: boolean;
  className?: string;
}

/**
 * File input styled as an outlined button plus the chosen file's name. The native input stays
 * in the DOM (visually hidden) so it is still labelled and testable.
 */
export function FilePicker({
  label,
  accept,
  file,
  onChange,
  helper,
  error,
  disabled,
  className,
}: FilePickerProps) {
  const id = useId();
  const helperId = helper ? `${id}-helper` : undefined;
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-body-s text-on-surface-variant">
        {label}
      </label>
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="outlined"
          size="sm"
          icon="folder"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          aria-describedby={id}
        >
          {file ? 'Change file' : 'Choose a file'}
        </Button>
        <span
          className={cn('min-w-0 truncate text-body-m', file ? 'text-on-surface' : 'text-on-surface-variant')}
        >
          {file ? file.name : 'No file chosen'}
        </span>
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept={accept}
          disabled={disabled}
          aria-describedby={helperId}
          aria-invalid={error || undefined}
          className="sr-only"
          onChange={(e) => {
            onChange(e.currentTarget.files?.[0] ?? null);
            e.currentTarget.value = '';
          }}
        />
      </div>
      {helper && (
        <div
          id={helperId}
          className={cn('px-1 text-body-s', error ? 'text-error' : 'text-on-surface-variant')}
        >
          {helper}
        </div>
      )}
    </div>
  );
}
