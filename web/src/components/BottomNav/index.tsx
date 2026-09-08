import { cn } from '@/lib/cn';
import { NavRailItem, type NavDestination } from '@/components/NavRail';

export interface BottomNavProps<K extends string = string> {
  destinations: NavDestination<K>[];
  value: K;
  onChange: (key: K) => void;
  className?: string;
}

/** M3 bottom navigation bar, 80 px, fixed to the bottom (< 840 px). Same destinations as the rail. */
export function BottomNav<K extends string = string>({
  destinations,
  value,
  onChange,
  className,
}: BottomNavProps<K>) {
  return (
    <nav
      aria-label="Sections"
      className={cn(
        'fixed inset-x-0 bottom-0 z-20 flex h-20 items-start justify-around bg-surface-container px-2 pt-3 pb-4',
        className,
      )}
    >
      {destinations.map((d) => (
        <NavRailItem
          key={d.key}
          destination={d}
          active={d.key === value}
          onSelect={() => onChange(d.key)}
          wide
        />
      ))}
    </nav>
  );
}
