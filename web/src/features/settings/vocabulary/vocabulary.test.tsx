import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { http, HttpResponse, server, TEST_TOKEN } from '@/test/msw';
import * as fx from '@/test/fixtures';
import { tokenStore } from '@/api/token';
import {
  parseVocabularyLines,
  parseVocabularyText,
  serializeVocabularyText,
  type VocabEntryInput,
} from '@/api/hooks/vocabulary';
import { VocabularySection } from './VocabularySection';
import { resetKeptVocabularyDraft } from './useVocabularyEditor';

// The draft is kept across mounts on purpose; start every test clean.
beforeEach(() => resetKeptVocabularyDraft());

/** The old dashboard's parseVocabEditor, kept here as the reference the new parser must match. */
function oldParseVocabEditor(text: string): { term: string; aliases: string[] }[] {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'))
    .map((l) => {
      const [term, rest] = l.split(/=(.*)/s);
      return {
        term: term.trim(),
        aliases: (rest || '')
          .split(',')
          .map((a) => a.trim())
          .filter(Boolean),
      };
    })
    .filter((e) => e.term);
}
function oldIgnoredVocabLines(text: string): number {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'))
    .filter((l) => !l.split(/=(.*)/s)[0].trim()).length;
}

const SAMPLE =
  '# People\nAlex\nMorgan\n\n# Places and things\nPlaud\nParrot Deck = Parted Deck, Carrot Deck\n = orphan\nScriberr = Scribber, Scriber\nA=B=C = x=y, z';

describe('vocabulary text format', () => {
  it('parses exactly like the old dashboard', () => {
    const parsed = parseVocabularyText(SAMPLE);
    expect(parsed.entries).toEqual(oldParseVocabEditor(SAMPLE));
    expect(parsed.ignored).toBe(oldIgnoredVocabLines(SAMPLE));
    expect(parsed.ignored).toBe(1);
  });

  it('round-trips the server editor_text through parse and serialize', () => {
    const text = fx.vocabulary.editor_text;
    const { entries } = parseVocabularyText(text);
    expect(serializeVocabularyText(entries)).toBe(text);
    expect(serializeVocabularyText(fx.vocabulary.entries)).toBe(text);
    // The server writes editor_text sorted by lower-cased term (vocabulary.to_editor_text).
    expect(serializeVocabularyText(fx.vocabulary.entries, { sorted: true })).toBe(
      'Obsidian\nParrot Deck = Parted Deck, Carrot Deck',
    );
    const serverText = 'alex\nMorgan = Morgen\nPlaud';
    expect(serializeVocabularyText(parseVocabularyText(serverText).entries, { sorted: true })).toBe(
      serverText,
    );
  });

  it('classifies lines so the list view can edit them in place', () => {
    const kinds = parseVocabularyLines('# note\nAlex\n\n = x\nB = c').map((l) => l.kind);
    expect(kinds).toEqual(['comment', 'entry', 'blank', 'ignored', 'entry']);
  });
});

function vocabHandler(body: typeof fx.vocabulary, seen: { gets: number }) {
  return http.get('/api/v1/vocabulary', () => {
    seen.gets++;
    return HttpResponse.json(body);
  });
}

describe('VocabularySection', () => {
  it('lists terms with their mis-hearings and the counts', async () => {
    renderWithProviders(<VocabularySection />);
    const list = await screen.findByRole('list', { name: 'Vocabulary terms' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Parrot Deck');
    expect(items[0]).toHaveTextContent('Heard as Parted Deck, Carrot Deck');
    expect(items[1]).toHaveTextContent('Obsidian');
    expect(items[1]).not.toHaveTextContent('Heard as');
    expect(screen.getByText('2 terms · 1 with corrections')).toBeInTheDocument();
    expect(screen.getByText('Saved · applies to new transcriptions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Revert' })).toBeDisabled();
  });

  it('filters rows by term or mis-hearing', async () => {
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.type(screen.getByRole('searchbox', { name: 'Find a term' }), 'carrot');
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent('Parrot Deck');
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Find a term' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Find a term' }), 'zzz');
    expect(screen.getByText('No terms match.')).toBeInTheDocument();
  });

  it('tracks dirty edits, saves the entries with their sources, and adopts the server text', async () => {
    const seen = { gets: 0 };
    let put: { entries: VocabEntryInput[] } | null = null;
    const withSources = {
      ...fx.vocabulary,
      entries: [{ ...fx.vocabulary.entries[0], source: 'obsidian' as const }, fx.vocabulary.entries[1]],
    };
    server.use(
      vocabHandler(withSources, seen),
      http.put('/api/v1/vocabulary', async ({ request }) => {
        put = (await request.json()) as { entries: VocabEntryInput[] };
        return HttpResponse.json({ entries: put.entries });
      }),
    );
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });

    await userEvent.click(screen.getByRole('button', { name: 'Edit Obsidian' }));
    const form = screen.getByRole('form', { name: 'Edit Obsidian' });
    await userEvent.type(within(form).getByLabelText(/Heard as/), 'Obsidion, Absidian');
    await userEvent.click(within(form).getByRole('button', { name: 'Done' }));

    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Revert' })).toBeEnabled();
    const save = screen.getByRole('button', { name: 'Save' });
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() => expect(put).not.toBeNull());
    expect(put!.entries).toEqual([
      { term: 'Parrot Deck', aliases: ['Parted Deck', 'Carrot Deck'], source: 'obsidian' },
      { term: 'Obsidian', aliases: ['Obsidion', 'Absidian'], source: 'manual' },
    ]);
    expect(
      await screen.findByText('Vocabulary saved. It applies to new transcriptions.'),
    ).toBeInTheDocument();
    // The refetch after save brings the server text back; the editor follows it again.
    await waitFor(() => expect(seen.gets).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled());
  });

  it('never overwrites local edits when a refetch brings new server text; Revert adopts it', async () => {
    const seen = { gets: 0 };
    server.use(vocabHandler(fx.vocabulary, seen));
    const { queryClient } = renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });

    // Local edit: add a term.
    await userEvent.click(screen.getByRole('button', { name: 'Add a term' }));
    const form = screen.getByRole('form', { name: 'New term' });
    await userEvent.type(within(form).getByLabelText('Term'), 'Kirkland');
    await userEvent.click(within(form).getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);

    // Another tab saved meanwhile: the server text changes and a poll/refetch brings it.
    server.use(
      vocabHandler(
        {
          entries: [{ term: 'Morgan', aliases: [], source: 'manual', weight: 0 }],
          editor_text: 'Morgan',
          hotwords: 'Morgan',
        },
        seen,
      ),
    );
    await queryClient.invalidateQueries({ queryKey: ['vocabulary'] });
    await waitFor(() => expect(seen.gets).toBeGreaterThanOrEqual(2));

    // Local edits stay put.
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[2]).toHaveTextContent('Kirkland');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();

    // Revert drops them and shows what the server has now.
    await userEvent.click(screen.getByRole('button', { name: 'Revert' }));
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(1));
    expect(screen.getByRole('listitem')).toHaveTextContent('Morgan');
    expect(screen.getByText('Saved · applies to new transcriptions')).toBeInTheDocument();
  });

  it('edits the raw text too, counting lines that would be ignored, and removes rows', async () => {
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('radio', { name: 'Text' }));
    const ta = screen.getByRole('textbox', { name: 'Vocabulary text' });
    expect(ta).toHaveValue(fx.vocabulary.editor_text);
    await userEvent.type(ta, '\n = nothing before');
    expect(screen.getByText(/1 line will be ignored \(nothing before the equals sign\)/)).toBeInTheDocument();
    expect(screen.getByText(/Unsaved changes/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('radio', { name: 'List' }));
    await userEvent.click(screen.getByRole('button', { name: 'Remove Obsidian' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('1 term · 1 with corrections')).toBeInTheDocument();
  });

  it('rejects duplicate and malformed terms inline', async () => {
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Add a term' }));
    const form = screen.getByRole('form', { name: 'New term' });
    await userEvent.type(within(form).getByLabelText('Term'), 'obsidian');
    await userEvent.click(within(form).getByRole('button', { name: 'Add' }));
    expect(screen.getByRole('alert')).toHaveTextContent('You already have this term.');
    await userEvent.clear(within(form).getByLabelText('Term'));
    await userEvent.type(within(form).getByLabelText('Term'), 'a = b');
    await userEvent.click(within(form).getByRole('button', { name: 'Add' }));
    expect(screen.getByRole('alert')).toHaveTextContent("A term can't contain an equals sign.");
  });

  it('imports pasted terms and reports how many were added', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/vocabulary/import', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ entries: fx.vocabulary.entries, added: 3 });
      }),
    );
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Import…' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    expect(within(dialog).getByText('Nothing to import.')).toBeInTheDocument();

    await userEvent.type(
      within(dialog).getByLabelText('Or paste here'),
      'Kirkland{enter}# note{enter}Scriberr = Scribber, Scriber',
    );
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      entries: [
        { term: 'Kirkland', aliases: [] },
        { term: 'Scriberr', aliases: ['Scribber', 'Scriber'] },
      ],
    });
    expect(await screen.findByText('3 terms added')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('imports from a picked text file', async () => {
    let body: unknown = null;
    server.use(
      http.post('/api/v1/vocabulary/import', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ entries: fx.vocabulary.entries, added: 0 });
      }),
    );
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Import…' }));
    const dialog = screen.getByRole('dialog');
    const file = new File(['Alex\nMorgan = Morgen\n'], 'names.txt', { type: 'text/plain' });
    await userEvent.upload(within(dialog).getByLabelText('Text file'), file);
    await waitFor(() =>
      expect(within(dialog).getByLabelText('Or paste here')).toHaveValue('Alex\nMorgan = Morgen\n'),
    );
    expect(within(dialog).getByText('names.txt')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      entries: [
        { term: 'Alex', aliases: [] },
        { term: 'Morgan', aliases: ['Morgen'] },
      ],
    });
    expect(await screen.findByText('Nothing new to add')).toBeInTheDocument();
  });

  it('explains when the server has no vocabulary feature', async () => {
    server.use(
      http.get('/api/v1/vocabulary', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })),
    );
    renderWithProviders(<VocabularySection />);
    expect(await screen.findByText("Your server doesn't support custom vocabulary yet.")).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });

  it('keeps unsaved edits when the page unmounts and comes back (section switch)', async () => {
    const { unmount } = renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Remove Obsidian' }));
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    unmount();

    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Revert' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('guards the tab against closing while a draft is kept, even from another section', async () => {
    const fire = () => {
      const e = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(e);
      return e.defaultPrevented;
    };
    const { unmount } = renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    expect(fire()).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Remove Obsidian' }));
    expect(fire()).toBe(true);
    unmount(); // switched to another section: the draft is kept, so is the guard
    expect(fire()).toBe(true);
    resetKeptVocabularyDraft();
    expect(fire()).toBe(false);
  });

  it('forgets the kept draft on sign-out', async () => {
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Remove Obsidian' }));
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    tokenStore.clear();
    tokenStore.set(TEST_TOKEN);
    cleanup();
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.queryByText('Unsaved changes')).toBeNull();
  });

  it('locks other rows while one is being edited', async () => {
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Edit Parrot Deck' }));
    expect(screen.getByRole('button', { name: 'Remove Obsidian' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Edit Obsidian' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Add a term' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Remove Obsidian' })).toBeEnabled();
  });

  it('shows the saved list at once, even before the refetch answers', async () => {
    const gate: { release: (() => void) | null } = { release: null };
    let gets = 0;
    server.use(
      http.get('/api/v1/vocabulary', async () => {
        gets++;
        if (gets > 1) await new Promise<void>((r) => (gate.release = r));
        return HttpResponse.json(fx.vocabulary);
      }),
      http.put('/api/v1/vocabulary', async ({ request }) => {
        const { entries } = (await request.json()) as { entries: unknown[] };
        return HttpResponse.json({ entries });
      }),
    );
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Remove Obsidian' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await screen.findByText('Vocabulary saved. It applies to new transcriptions.');
    // The GET is still pending; the list already reflects what the server accepted.
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText('Saved · applies to new transcriptions')).toBeInTheDocument();
    gate.release?.();
  });

  it('drops pasted text when a picked file is rejected, so nothing stale is imported', async () => {
    renderWithProviders(<VocabularySection />);
    await screen.findByRole('list', { name: 'Vocabulary terms' });
    await userEvent.click(screen.getByRole('button', { name: 'Import…' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Or paste here'), 'Kirkland');
    const big = new File([new Uint8Array(2_000_001)], 'huge.txt', { type: 'text/plain' });
    await userEvent.upload(within(dialog).getByLabelText('Text file'), big);
    expect(within(dialog).getByText('That file is too large.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Or paste here')).toHaveValue('');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }));
    expect(within(dialog).getByText('Nothing to import.')).toBeInTheDocument();
  });
});
