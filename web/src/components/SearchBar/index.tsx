import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/IconButton';

export interface SearchBarProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> {
  value: string;
  onChange: (value: string) => void;
  /** Trailing action (the filter icon). Hidden while there is text: the clear button takes its place. */
  trailing?: ReactNode;
  /** Wrapper class (width, margins). */
  className?: string;
}

/** 56 px pill on surface-container-high with a leading search glyph and a clear button. */
export const SearchBar = forwardRef<HTMLInputElement, SearchBarProps>(function SearchBar(
  {
    value,
    onChange,
    trailing,
    className,
    placeholder = 'Search recordings',
    'aria-label': ariaLabel,
    ...rest
  },
  ref,
) {
  return (
    <div
      role="search"
      className={cn(
        'flex h-14 items-center gap-1 rounded-full bg-surface-container-high pl-1 pr-2 text-on-surface',
        className,
      )}
    >
      <span className="inline-grid size-10 shrink-0 place-items-center text-on-surface-variant">
        <Icon name="search" size={20} />
      </span>
      <input
        ref={ref}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        className="h-full min-w-0 flex-1 bg-transparent px-1 text-body-l outline-none placeholder:text-on-surface-variant [&::-webkit-search-cancel-button]:hidden"
        {...rest}
      />
      {value ? <IconButton icon="close" label="Clear search" onClick={() => onChange('')} /> : trailing}
    </div>
  );
});
