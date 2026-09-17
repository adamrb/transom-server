import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import { AndroidAppSection } from './AndroidAppSection';
import { validateApkForm } from './ApkUploadDialog';

const apkFile = (name = 'app.apk', size = 1024) =>
  new File([new Uint8Array(size)], name, { type: 'application/vnd.android.package-archive' });

describe('validateApkForm', () => {
  const base = { file: apkFile(), versionCode: '16', versionName: '0.6.0', minSdk: '', notes: '' };
  it('mirrors the old dashboard checks', () => {
    expect(validateApkForm({ ...base, file: null }, fx.apkInfo)).toEqual({
      ok: false,
      error: 'Choose an .apk file.',
    });
    expect(validateApkForm({ ...base, versionCode: '' }, null)).toEqual({
      ok: false,
      error: 'The version code must be a whole number above zero.',
    });
    expect(validateApkForm({ ...base, versionCode: '0' }, null).ok).toBe(false);
    expect(validateApkForm({ ...base, versionCode: '3' }, fx.apkInfo)).toEqual({
      ok: false,
      error: 'The version code must be at least 15, the one hosted now.',
    });
    expect(validateApkForm({ ...base, versionName: ' ' }, null)).toEqual({
      ok: false,
      error: 'Enter a version name.',
    });
    expect(validateApkForm({ ...base, versionName: 'x'.repeat(51) }, null)).toEqual({
      ok: false,
      error: 'The version name must be 50 characters or fewer.',
    });
    expect(validateApkForm({ ...base, notes: '  Fixes.  ' }, fx.apkInfo)).toEqual({
      ok: true,
      metadata: { version_code: 16, version_name: '0.6.0', notes: 'Fixes.' },
    });
    // same code as hosted is allowed (replace), notes omitted when blank
    expect(validateApkForm({ ...base, versionCode: '15' }, fx.apkInfo)).toEqual({
      ok: true,
      metadata: { version_code: 15, version_name: '0.6.0' },
    });
    // optional minimum API level
    expect(validateApkForm({ ...base, minSdk: '26' }, null)).toEqual({
      ok: true,
      metadata: { version_code: 16, version_name: '0.6.0', min_sdk: 26 },
    });
    expect(validateApkForm({ ...base, minSdk: '0' }, null)).toEqual({
      ok: false,
      error: 'The minimum Android API level must be a whole number above zero.',
    });
  });
});

describe('AndroidAppSection', () => {
  it('shows the hosted version, size, upload time and notes, and copies the checksum', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderWithProviders(<AndroidAppSection />);
    expect(await screen.findByText(/Version 0\.5\.0/)).toBeInTheDocument();
    expect(screen.getByText('(build 15)')).toBeInTheDocument();
    expect(screen.getByText(/21\.8 MB · uploaded /)).toBeInTheDocument();
    expect(screen.getByText('UX overhaul.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Copy checksum' }));
    expect(writeText).toHaveBeenCalledWith(fx.apkInfo.sha256);
    expect(await screen.findByText('Checksum copied')).toBeInTheDocument();
  });

  it('downloads the APK as a blob with the hosted filename', async () => {
    server.use(
      http.get(
        '/api/v1/apk/file',
        () =>
          new HttpResponse(new Uint8Array([1, 2, 3]), {
            headers: {
              'Content-Type': 'application/vnd.android.package-archive',
              'Content-Disposition': 'attachment; filename="15-app.apk"',
            },
          }),
      ),
    );
    const createObjectURL = vi.fn(() => 'blob:apk');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderWithProviders(<AndroidAppSection />);
    await userEvent.click(await screen.findByRole('button', { name: 'Download APK' }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(createObjectURL).toHaveBeenCalled();
    const anchor = click.mock.contexts[0] as unknown as HTMLAnchorElement;
    expect(anchor.download).toBe('15-app.apk');
    click.mockRestore();
  });

  it('shows the empty state when nothing is hosted', async () => {
    server.use(
      http.get('/api/v1/apk/info', () => HttpResponse.json({ detail: 'No APK is hosted.' }, { status: 404 })),
    );
    renderWithProviders(<AndroidAppSection />);
    expect(await screen.findByText('No app hosted yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Download APK' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Upload a new version' })).toBeInTheDocument();
  });

  it('uploads a new version with metadata and progress, then shows it', async () => {
    // jsdom's XHR hands MSW a body without its multipart content type, so capture what went into
    // the FormData and let MSW answer the request.
    const append = vi.spyOn(FormData.prototype, 'append');
    let posted = 0;
    server.use(
      http.post('/api/v1/apk', () => {
        posted++;
        return HttpResponse.json(
          {
            ...fx.apkInfo,
            version_code: 16,
            version_name: '0.6.0',
            notes: 'Faster.',
            filename: '16-app.apk',
          },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(<AndroidAppSection />);
    await screen.findByText(/Version 0\.5\.0/);
    await userEvent.click(screen.getByRole('button', { name: 'Upload a new version' }));
    const dialog = screen.getByRole('dialog');

    // Validation runs in the old order.
    await userEvent.click(within(dialog).getByRole('button', { name: 'Upload' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Choose an .apk file.');
    await userEvent.upload(within(dialog).getByLabelText('APK file'), apkFile('transom.apk'));
    expect(within(dialog).getByText('transom.apk')).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText('Version code'), '3');
    await userEvent.type(within(dialog).getByLabelText('Version name'), '0.6.0');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Upload' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent(
      'The version code must be at least 15, the one hosted now.',
    );
    await userEvent.clear(within(dialog).getByLabelText('Version code'));
    await userEvent.type(within(dialog).getByLabelText('Version code'), '16');
    await userEvent.type(within(dialog).getByLabelText('Release notes (optional)'), 'Faster.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(posted).toBe(1));
    const fields = Object.fromEntries(append.mock.calls.map(([k, v]) => [k, v]));
    expect((fields.file as File).name).toBe('transom.apk');
    expect(JSON.parse(String(fields.metadata))).toEqual({
      version_code: 16,
      version_name: '0.6.0',
      notes: 'Faster.',
    });
    expect(await screen.findByText('New app version hosted')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText(/Version 0\.6\.0/)).toBeInTheDocument();
    expect(screen.getByText('Faster.')).toBeInTheDocument();
    append.mockRestore();
  });

  it('shows the server sentence when an upload is refused', async () => {
    server.use(
      http.post('/api/v1/apk', () =>
        HttpResponse.json({ detail: 'That file is not an Android package.' }, { status: 400 }),
      ),
    );
    renderWithProviders(<AndroidAppSection />);
    await screen.findByText(/Version 0\.5\.0/);
    await userEvent.click(screen.getByRole('button', { name: 'Upload a new version' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.upload(within(dialog).getByLabelText('APK file'), apkFile());
    await userEvent.type(within(dialog).getByLabelText('Version code'), '16');
    await userEvent.type(within(dialog).getByLabelText('Version name'), '0.6.0');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Upload' }));
    expect(await within(dialog).findByText('That file is not an Android package.')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('removes the hosted app after confirming', async () => {
    let deleted = false;
    server.use(
      http.delete('/api/v1/apk', () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<AndroidAppSection />);
    await screen.findByText(/Version 0\.5\.0/);
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Stop hosting the app?');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(deleted).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText('App removed')).toBeInTheDocument();
    expect(await screen.findByText('No app hosted yet')).toBeInTheDocument();
  });
});
