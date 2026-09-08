/**
 * Visual QA gallery: every component in every variant, light and dark. Development only
 * (#/dev/components with `npm run dev`). Not part of the production bundle.
 */
import { useRef, useState, type ReactNode } from 'react';
import {
  Avatar,
  Banner,
  Button,
  Card,
  Chip,
  ConfirmDialog,
  CopyField,
  Dialog,
  EmptyState,
  FilePicker,
  Icon,
  ICON_NAMES,
  IconButton,
  LinearProgress,
  ListItem,
  Markdown,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  Popover,
  ProgressRing,
  RadioGroup,
  SearchBar,
  SegmentedButton,
  Select,
  Skeleton,
  SkeletonListItem,
  SkeletonText,
  SkipIcon,
  Slider,
  StatusChip,
  Switch,
  Tabs,
  TextField,
  TopAppBar,
  useSnackbar,
} from '@/components';
import { useTheme, type ThemeChoice } from '@/theme';
import { SectionAppBar } from '@/features/shell/SectionAppBar';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="m-0 mb-3 font-display text-title-l text-on-surface">{title}</h2>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  );
}

export default function ComponentGallery() {
  const { theme, setTheme } = useTheme();
  const snackbar = useSnackbar();
  const [q, setQ] = useState('');
  const [sw, setSw] = useState(true);
  const [slider, setSlider] = useState(40);
  const [tab, setTab] = useState<'summary' | 'transcript' | 'more'>('summary');
  const [menuOpen, setMenuOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [kind, setKind] = useState<'webhook' | 'markdown' | 'none'>('webhook');
  const [picked, setPicked] = useState<'a' | 'b' | 'c' | null>('a');
  const [file, setFile] = useState<File | null>(null);
  const menuAnchor = useRef<HTMLButtonElement>(null);
  const sheetAnchor = useRef<HTMLButtonElement>(null);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SectionAppBar
        title="Components"
        actions={
          <SegmentedButton<ThemeChoice>
            label="Theme"
            size="sm"
            value={theme}
            onChange={setTheme}
            options={[
              { key: 'system', label: 'System', icon: 'contrast' },
              { key: 'light', label: 'Light', icon: 'light_mode' },
              { key: 'dark', label: 'Dark', icon: 'dark_mode' },
            ]}
          />
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-(--content-top-pad) pb-(--content-bottom-pad) max-md:px-4">
        <div className="mx-auto max-w-[960px] pt-2">
          <Section title="Type scale">
            <div className="flex w-full flex-col gap-1">
              <div className="font-display text-display-s">Display S · Roboto Flex 300</div>
              <div className="font-display text-headline-l">Headline L · page titles</div>
              <div className="font-display text-headline-m">Headline M · recording title</div>
              <div className="font-display text-title-l">Title L · section heads</div>
              <div className="text-title-m">Title M · card headings</div>
              <div className="text-body-l">Body L · list headlines and inputs</div>
              <div className="text-body-m text-on-surface-variant">Body M · supporting text</div>
              <div className="text-transcript text-on-surface-body">Transcript · 15/26 on-surface-body</div>
              <div className="text-label-l">Label L · buttons, chips</div>
              <div className="text-label-m">LABEL M · status words</div>
              <div className="font-mono text-mono">Roboto Mono · vocabulary editor</div>
            </div>
          </Section>

          <Section title="Colour roles">
            {(
              [
                ['surface', 'bg-surface text-on-surface'],
                ['container-lowest', 'bg-surface-container-lowest text-on-surface'],
                ['container-low', 'bg-surface-container-low text-on-surface'],
                ['container', 'bg-surface-container text-on-surface'],
                ['container-high', 'bg-surface-container-high text-on-surface'],
                ['container-highest', 'bg-surface-container-highest text-on-surface'],
                ['primary', 'bg-primary text-on-primary'],
                ['secondary-container', 'bg-secondary-container text-on-secondary-container'],
                ['error-container', 'bg-error-container text-on-error-container'],
                ['success-container', 'bg-success-container text-on-success-container'],
                ['warning-container', 'bg-warning-container text-on-warning-container'],
                ['inverse', 'bg-inverse-surface text-inverse-on-surface'],
                ['spk1', 'bg-spk1 text-on-spk1'],
                ['spk2', 'bg-spk2 text-on-spk2'],
                ['spk3', 'bg-spk3 text-on-spk3'],
                ['spk4', 'bg-spk4 text-on-spk4'],
              ] as const
            ).map(([name, cls]) => (
              <div
                key={name}
                className={`grid h-14 w-36 place-items-center rounded-md text-label-m shadow-e1 ${cls}`}
              >
                {name}
              </div>
            ))}
          </Section>

          <Section title="Buttons">
            <Button variant="filled" icon="send">
              Run again
            </Button>
            <Button variant="tonal" icon="add">
              Add rule
            </Button>
            <Button variant="outlined" icon="refresh">
              Retry
            </Button>
            <Button variant="text" icon="edit">
              Edit
            </Button>
            <Button variant="danger">Delete</Button>
            <Button variant="filled" loading>
              Saving
            </Button>
            <Button variant="filled" disabled>
              Disabled
            </Button>
            <Button variant="tonal" size="sm" icon="download">
              Small tonal
            </Button>
            <Button variant="outlined" size="sm">
              Small outlined
            </Button>
            <Button variant="text" size="sm">
              Small text
            </Button>
          </Section>

          <Section title="Icon buttons">
            <IconButton icon="more_vert" label="More" />
            <IconButton icon="format_list_bulleted" label="Jump to" selected />
            <IconButton icon="content_copy" label="Copy" variant="tonal" />
            <IconButton icon="play_arrow" label="Play" variant="filled" size="lg" />
            <IconButton icon="pause" label="Pause" variant="filled" size="xl" />
            <IconButton icon="replay_10" label="Back" />
            <IconButton icon="forward_30" label="Forward" />
            <IconButton icon="close" label="Close" disabled />
          </Section>

          <Section title="Chips and status words">
            <Chip variant="filter" selected>
              All
            </Chip>
            <Chip variant="filter">Waiting</Chip>
            <Chip variant="filter">Transcribing</Chip>
            <Chip variant="filter">Failed</Chip>
            <Chip variant="filter">No speech</Chip>
            <Chip icon="content_copy">Copy transcript</Chip>
            <Chip icon="ios_share">Export markdown</Chip>
            <Chip icon="download">Download audio</Chip>
            <StatusChip tone="inflight">Transcribing 42%</StatusChip>
            <StatusChip tone="inflight">Waiting</StatusChip>
            <StatusChip tone="failed">Failed</StatusChip>
            <StatusChip tone="neutral">No speech</StatusChip>
            <StatusChip tone="neutral">Not transcribed</StatusChip>
            <StatusChip tone="ok">this computer</StatusChip>
            <StatusChip tone="tag" icon="group">
              2 speakers
            </StatusChip>
            <StatusChip tone="star" icon="star_fill">
              2
            </StatusChip>
          </Section>

          <Section title="Avatars">
            <Avatar kind="waveform" />
            <Avatar kind="group" />
            <Avatar kind="silent" />
            <Avatar kind="waiting" label="Waiting" />
            <Avatar kind="progress" value={0.42} label="Transcribing" />
            <Avatar kind="failed" />
            <Avatar kind="icon" icon="palette" size={40} shape="rounded" />
            <Avatar kind="text" text="1" size={40} />
            <ProgressRing value={0.7} tone="primary" size={48} stroke={4} showValue />
            <ProgressRing size={28} />
          </Section>

          <Section title="Cards">
            <Card
              title="Summary"
              actions={<IconButton icon="content_copy" label="Copy summary" />}
              className="w-[320px]"
            >
              <Markdown>
                {'**Main point.** Data centre backlash is bipartisan.\n\n- Quincy, WA\n- Loudoun County, VA'}
              </Markdown>
            </Card>
            <Card tone="low" className="w-[280px]" title="Getting started">
              <div className="text-body-m text-on-surface-variant">
                Three steps and your recordings show up here.
              </div>
            </Card>
            <Card tone="high" elevation={2} className="w-[280px]">
              <div className="text-title-m">Player card</div>
              <Slider
                value={slider}
                max={100}
                markers={[12, 64]}
                onChange={setSlider}
                label="Position"
                formatValue={(v) => `${v}s`}
              />
              <div className="mt-1 flex items-center justify-between text-[13px] text-on-surface-variant tnum">
                <span>1:09:53</span>
                <span>2:19:46</span>
              </div>
            </Card>
          </Section>

          <Section title="List items">
            <div className="flex w-full max-w-[480px] flex-col gap-1.5">
              <ListItem
                leading={<Avatar kind="waiting" label="Waiting" />}
                headline="Recording from 5:55 PM"
                supporting={
                  <>
                    <StatusChip tone="inflight">Waiting</StatusChip>
                    <span className="truncate">Your server will start on it shortly</span>
                  </>
                }
                trailing="5:55 PM"
                onClick={() => snackbar.show('Opened')}
              />
              <ListItem
                leading={<Avatar kind="progress" value={0.42} label="Transcribing" />}
                headline="Recording from 5:52 PM"
                supporting={
                  <>
                    <StatusChip tone="inflight">Transcribing 42%</StatusChip>
                    <span className="truncate">The transcript appears as soon as it is ready</span>
                  </>
                }
                trailing="5:52 PM"
                onClick={() => {}}
              />
              <ListItem
                selected
                leading={<Avatar kind="group" selected />}
                headline="The Political Fight Over AI Data Centers"
                supporting="12:25 AM · 2h 19m · Everyone, it appears, hates datacenters."
                trailing={
                  <StatusChip tone="star" icon="star_fill">
                    2
                  </StatusChip>
                }
                onClick={() => {}}
              />
              <ListItem
                leading={<Avatar kind="silent" />}
                headline="Silent recording"
                supporting={
                  <>
                    <StatusChip tone="neutral">No speech</StatusChip>
                    <span>1:38 AM · 4s</span>
                  </>
                }
                onClick={() => {}}
              />
              <ListItem
                leading={<Avatar kind="failed" />}
                headline="Standup notes, sprint 42"
                supporting={
                  <>
                    <StatusChip tone="failed">Failed</StatusChip>
                    <span className="truncate">Couldn't read the audio file.</span>
                  </>
                }
                trailing="9:05 AM"
                onClick={() => {}}
              />
              <Card padding="tight">
                <ListItem
                  shape="flat"
                  leading={<Avatar kind="icon" icon="computer" size={40} shape="rounded" />}
                  headline={
                    <span className="flex items-center gap-2">
                      Chrome on Linux <StatusChip tone="ok">this computer</StatusChip>
                    </span>
                  }
                  supporting="Signed in Today 3:48 PM · last used Today 5:52 PM"
                  trailing={
                    <Button variant="danger" size="sm">
                      Sign out
                    </Button>
                  }
                />
                <ListItem
                  shape="flat"
                  leading={<Avatar kind="icon" icon="qr_code" size={40} shape="rounded" />}
                  headline="Connect a phone"
                  supporting="Link the Plaud Bridge app on a phone to this server."
                  trailing={
                    <Button variant="tonal" size="sm" icon="qr_code">
                      Connect
                    </Button>
                  }
                />
              </Card>
            </div>
          </Section>

          <Section title="Inputs">
            <SearchBar
              value={q}
              onChange={setQ}
              className="w-full max-w-[400px]"
              trailing={<IconButton icon="tune" label="Filters" />}
            />
            <TextField label="Rule name" defaultValue="Ask Claude" className="w-[240px]" />
            <TextField
              label="Webhook URL"
              placeholder="https://"
              error
              helper="Type a web address."
              className="w-[240px]"
            />
            <TextField icon="search" size="sm" placeholder="Find in transcript" className="w-[220px]" />
            <TextField
              label="Secret header"
              type="password"
              placeholder="Set. Leave blank to keep it."
              trailing={<IconButton icon="visibility" label="Show" />}
              className="w-[280px]"
            />
            <TextField
              multiline
              label="Description"
              placeholder="What this rule is for"
              className="w-full max-w-[400px]"
            />
            <TextField
              multiline
              tonal
              mono
              aria-label="Vocabulary"
              defaultValue={'# People\nAlex\nPlaud Bridge = Plogged Bridge, Plod Bridge'}
              className="w-full max-w-[400px]"
            />
            <Switch checked={sw} onChange={setSw} label="Turn the rule on or off" />
            <Switch checked={!sw} onChange={(v) => setSw(!v)} label="Inverse" />
            <Switch checked disabled onChange={() => {}} label="Disabled" />
            <SegmentedButton
              label="Theme"
              value={theme}
              onChange={setTheme}
              options={[
                { key: 'system', label: 'System', icon: 'contrast' },
                { key: 'light', label: 'Light', icon: 'light_mode' },
                { key: 'dark', label: 'Dark', icon: 'dark_mode' },
              ]}
            />
            <div className="w-full max-w-[400px]">
              <Tabs
                label="Detail"
                value={tab}
                onChange={setTab}
                tabs={[
                  { key: 'summary', label: 'Summary', icon: 'description' },
                  { key: 'transcript', label: 'Transcript', icon: 'format_list_bulleted' },
                  { key: 'more', label: 'More', disabled: true },
                ]}
              />
            </div>
          </Section>

          <Section title="Radios, selects, copy fields, file pickers">
            <div className="w-full max-w-[400px]">
              <RadioGroup
                label="What happens"
                value={kind}
                onChange={setKind}
                options={[
                  {
                    key: 'webhook',
                    label: 'Send it to the agent',
                    description: 'Hands the transcript to your agent at a web address.',
                    icon: 'send',
                  },
                  {
                    key: 'markdown',
                    label: 'Save a note in a folder',
                    description: 'Writes a markdown note into your vault.',
                    icon: 'description',
                  },
                  { key: 'none', label: 'Just record the decision', icon: 'block', disabled: true },
                ]}
              />
            </div>
            <Select
              label="Recording"
              value={picked}
              onChange={setPicked}
              options={[
                {
                  value: 'a',
                  label: 'The Political Fight Over AI Data Centers',
                  description: 'Today 2:48 AM',
                },
                { value: 'b', label: 'Standup', description: 'Yesterday 9:02 AM' },
                { value: 'c', label: 'Silent memo', disabled: true },
              ]}
              className="w-[320px]"
            />
            <Select
              label="Recording"
              hideLabel
              size="sm"
              value={null}
              onChange={() => {}}
              options={[]}
              placeholder="No finished recordings yet"
              className="w-[280px]"
            />
            <CopyField label="Server address" value="https://plaud.example.net" className="w-[320px]" />
            <CopyField label="Access token" value="abcdefghijklmnopqrstuvwxyz" secret className="w-[320px]" />
            <FilePicker
              label="Text file"
              accept=".txt,.md"
              file={file}
              onChange={setFile}
              helper="One term per line."
              className="w-[320px]"
            />
            <div className="flex items-center gap-3 text-on-surface">
              <SkipIcon seconds={15} direction="back" />
              <SkipIcon seconds={30} direction="forward" />
              <SkipIcon seconds={10} direction="back" size={20} />
              <IconButton label="Back 15 seconds" className="text-on-surface">
                <SkipIcon seconds={15} direction="back" />
              </IconButton>
            </div>
            <div className="w-full max-w-[400px]">
              <Slider
                value={slider}
                max={100}
                buffered={Math.min(100, slider + 30)}
                markers={[15, 62]}
                onChange={setSlider}
                label="Position (buffered)"
              />
            </div>
          </Section>

          <Section title="Progress, skeletons, banners">
            <div className="w-full max-w-[400px]">
              <LinearProgress label="Loading" />
            </div>
            <div className="w-full max-w-[400px]">
              <LinearProgress value={0.6} />
            </div>
            <div className="w-full max-w-[400px]">
              <SkeletonListItem />
            </div>
            <div className="w-full max-w-[400px]">
              <SkeletonText lines={3} />
            </div>
            <Skeleton width={120} height={28} />
            <div className="flex w-full flex-col gap-2">
              <Banner tone="success">
                <b>Automations are on.</b> Two of three rules are turned on · last run Today 2:48 AM
              </Banner>
              <Banner
                tone="warning"
                action={
                  <Button variant="text" size="sm">
                    Retry
                  </Button>
                }
              >
                Can't reach your server
              </Banner>
              <Banner tone="error">Transcription isn't set up on the server.</Banner>
              <Banner tone="neutral">Recordings sync from the app on your phone.</Banner>
            </div>
          </Section>

          <Section title="Menus, sheets, dialogs, snackbar">
            <Button ref={menuAnchor} variant="outlined" icon="more_vert" onClick={() => setMenuOpen(true)}>
              Open menu (auto)
            </Button>
            <Button
              ref={sheetAnchor}
              variant="outlined"
              icon="format_list_bulleted"
              onClick={() => setSheetOpen(true)}
            >
              Open sheet
            </Button>
            <Button variant="outlined" onClick={() => setDialogOpen(true)}>
              Dialog (sm)
            </Button>
            <Button variant="outlined" onClick={() => setFormDialogOpen(true)}>
              Form dialog (md, full screen on phone)
            </Button>
            <Button variant="outlined" onClick={() => setConfirmOpen(true)}>
              Destructive confirm
            </Button>
            <Button variant="tonal" onClick={() => snackbar.show('Transcript copied')}>
              Snackbar
            </Button>
            <Button variant="tonal" onClick={() => snackbar.error("Couldn't export the transcript.")}>
              Error snackbar
            </Button>
            <Button
              variant="tonal"
              onClick={() =>
                snackbar.show('Deleted', {
                  action: { label: 'Undo', onClick: () => snackbar.show('Restored') },
                })
              }
            >
              With action
            </Button>
            <Popover open={menuOpen} onClose={() => setMenuOpen(false)} anchorRef={menuAnchor} label="More">
              <MenuItem icon="content_copy">Copy transcript</MenuItem>
              <MenuItem icon="ios_share">Export markdown</MenuItem>
              <MenuItem icon="download">Download audio</MenuItem>
              <MenuItem icon="edit">Rename</MenuItem>
              <MenuSeparator />
              <MenuItem icon="refresh">Transcribe again…</MenuItem>
              <MenuItem icon="delete" danger>
                Delete…
              </MenuItem>
            </Popover>
            <Popover
              open={sheetOpen}
              onClose={() => setSheetOpen(false)}
              anchorRef={sheetAnchor}
              as="sheet"
              title="Jump to"
            >
              <MenuLabel>Highlights</MenuLabel>
              <MenuItem time="1:36" icon="star_fill">
                Polls: 51% to 75%
              </MenuItem>
              <MenuItem time="47:35" icon="star_fill">
                Quincy and Loudoun County
              </MenuItem>
              <MenuSeparator />
              <MenuLabel>Speaker changes</MenuLabel>
              <MenuItem time="1:35">Speaker 2</MenuItem>
              <MenuItem time="1:36">Speaker 1</MenuItem>
            </Popover>
            <Dialog
              open={dialogOpen}
              onClose={() => setDialogOpen(false)}
              title="Rename recording"
              actions={
                <>
                  <Button variant="text" onClick={() => setDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={() => setDialogOpen(false)}>Save</Button>
                </>
              }
            >
              <TextField
                label="Name"
                defaultValue="The Political Fight Over AI Data Centers"
                className="mt-2"
              />
            </Dialog>
            <Dialog
              open={formDialogOpen}
              onClose={() => setFormDialogOpen(false)}
              title="New rule"
              size="md"
              fullScreen
              actions={
                <>
                  <Button variant="text" onClick={() => setFormDialogOpen(false)} className="max-md:hidden">
                    Cancel
                  </Button>
                  <Button onClick={() => setFormDialogOpen(false)}>Save</Button>
                </>
              }
            >
              <div className="flex flex-col gap-5 pt-1">
                <TextField label="Name" placeholder="Work meetings" />
                <TextField multiline label="When should this run?" rows={4} />
                <RadioGroup
                  label="What happens"
                  value={kind}
                  onChange={setKind}
                  options={[
                    { key: 'webhook', label: 'Send it to the agent', icon: 'send' },
                    { key: 'markdown', label: 'Save a note in a folder', icon: 'description' },
                    { key: 'none', label: 'Just record the decision', icon: 'block' },
                  ]}
                />
                <Select
                  label="Recording"
                  value={picked}
                  onChange={setPicked}
                  options={[
                    { value: 'a', label: 'The Political Fight Over AI Data Centers' },
                    { value: 'b', label: 'Standup' },
                    { value: 'c', label: 'Silent memo' },
                  ]}
                />
                <p>Long content scrolls inside the dialog while the title and the buttons stay put.</p>
                {Array.from({ length: 8 }, (_, i) => (
                  <p key={i}>Paragraph {i + 1} of filler so the body is taller than the viewport.</p>
                ))}
              </div>
            </Dialog>
            <ConfirmDialog
              open={confirmOpen}
              title="Delete this recording?"
              ok="Delete"
              danger
              onConfirm={() => setConfirmOpen(false)}
              onCancel={() => setConfirmOpen(false)}
            >
              <p>The audio and transcript are removed from the server. This cannot be undone.</p>
            </ConfirmDialog>
          </Section>

          <Section title="App bars and empty state">
            <div className="w-full rounded-lg bg-surface-container-low">
              <TopAppBar
                variant="small"
                as="div"
                leading={<IconButton icon="arrow_back" label="Back" />}
                title=""
                actions={
                  <>
                    <IconButton icon="format_list_bulleted" label="Jump to" />
                    <IconButton icon="more_vert" label="More" />
                  </>
                }
                className="bg-transparent"
              />
            </div>
            <div className="flex w-full">
              <EmptyState
                headline="No recordings yet"
                description="Recordings sync from the Plaud Bridge app on your phone and show up here a few seconds later."
                action={
                  <Button variant="tonal" icon="qr_code">
                    Connect a phone
                  </Button>
                }
              />
            </div>
          </Section>

          <Section title={`Icons (${ICON_NAMES.length})`}>
            {ICON_NAMES.map((n) => (
              <div
                key={n}
                className="flex w-24 flex-col items-center gap-1 text-center text-label-s text-on-surface-variant"
              >
                <Icon name={n} size={22} className="text-on-surface" />
                <span className="truncate w-full">{n}</span>
              </div>
            ))}
          </Section>
        </div>
      </div>
    </div>
  );
}
