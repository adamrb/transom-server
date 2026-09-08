import { Avatar, Card } from '@/components';

const STEPS = [
  ['Install the app on your phone', 'Settings › Android app has the download.'],
  ['Connect it to this server', 'Scan the code under Settings › Phone.'],
  ['Record', 'New recordings sync, transcribe and open here.'],
];

/** Desktop, nothing to show yet: the three-step card in the detail pane. */
export function GettingStarted() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card tone="low" className="w-[420px] max-w-full">
        <h3 className="m-0 mb-1 text-title-m text-on-surface">Getting started</h3>
        <p className="m-0 mb-2 text-body-m text-on-surface-variant">
          Three steps and your recordings show up here on their own.
        </p>
        <ol className="m-0 list-none p-0">
          {STEPS.map(([hd, su], i) => (
            <li
              key={i}
              className="flex items-center gap-4 border-t border-outline-variant py-3.5 first:border-t-0"
            >
              <Avatar kind="text" text={String(i + 1)} size={40} />
              <div className="min-w-0 flex-1">
                <div className="text-body-l text-on-surface">{hd}</div>
                <div className="text-body-m text-on-surface-variant">{su}</div>
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
