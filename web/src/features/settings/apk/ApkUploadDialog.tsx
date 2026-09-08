import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/Button';
import { Dialog } from '@/components/Dialog';
import { LinearProgress } from '@/components/LinearProgress';
import { TextField } from '@/components/TextField';
import { useSnackbar } from '@/components/Snackbar';
import { errorMessage } from '@/api/client';
import { useUploadApk } from '@/api/hooks/apk';
import type { ApkInfo, ApkMetadata } from '@/api/types';
import { fmtSize } from '@/lib/format';
import { FilePicker } from '../shared/FilePicker';

export interface ApkUploadDialogProps {
  open: boolean;
  onClose: () => void;
  /** The version hosted now, if any (the new version code must not go backwards). */
  hosted: ApkInfo | null;
}

export const VERSION_NAME_MAX = 50;
export const NOTES_MAX = 2000;

/**
 * Validate the upload form exactly as the old dashboard did. Returns the metadata to send, or
 * the sentence to show.
 */
export function validateApkForm(
  input: { file: File | null; versionCode: string; versionName: string; minSdk: string; notes: string },
  hosted: ApkInfo | null,
): { ok: true; metadata: ApkMetadata } | { ok: false; error: string } {
  const { file, versionName, notes } = input;
  const minSdkRaw = input.minSdk.trim();
  const minSdk = Math.floor(Number(minSdkRaw));
  const vcodeRaw = input.versionCode.trim();
  const vcode = Math.floor(Number(vcodeRaw));
  const vname = versionName.trim();
  if (!file) return { ok: false, error: 'Choose an .apk file.' };
  if (vcodeRaw === '' || !Number.isInteger(vcode) || vcode < 1)
    return { ok: false, error: 'The version code must be a whole number above zero.' };
  if (hosted && vcode < hosted.version_code)
    return {
      ok: false,
      error: `The version code must be at least ${hosted.version_code}, the one hosted now.`,
    };
  if (!vname) return { ok: false, error: 'Enter a version name.' };
  if (vname.length > VERSION_NAME_MAX)
    return { ok: false, error: `The version name must be ${VERSION_NAME_MAX} characters or fewer.` };
  if (minSdkRaw !== '' && (!Number.isInteger(minSdk) || minSdk < 1))
    return { ok: false, error: 'The minimum Android API level must be a whole number above zero.' };
  const metadata: ApkMetadata = { version_code: vcode, version_name: vname };
  if (minSdkRaw !== '') metadata.min_sdk = minSdk;
  const n = notes.trim();
  if (n) metadata.notes = n;
  return { ok: true, metadata };
}

/**
 * Upload a new version: the .apk, its version code and name, optional release notes. Shows the
 * upload progress; the dialog cannot be dismissed while the file is in flight.
 */
export function ApkUploadDialog({ open, onClose, hosted }: ApkUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [versionCode, setVersionCode] = useState('');
  const [versionName, setVersionName] = useState('');
  const [minSdk, setMinSdk] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const upload = useUploadApk();
  const snackbar = useSnackbar();

  useEffect(() => {
    if (open) {
      setFile(null);
      setVersionCode('');
      setVersionName('');
      setMinSdk('');
      setNotes('');
      setError(null);
      setProgress(null);
      upload.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens
  }, [open]);

  const busy = upload.isPending;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = validateApkForm({ file, versionCode, versionName, minSdk, notes }, hosted);
    if (!v.ok) return setError(v.error);
    setError(null);
    setProgress(null);
    upload.mutate(
      { file: file!, metadata: v.metadata, onProgress: setProgress },
      {
        onSuccess: () => {
          snackbar.show('New app version hosted');
          onClose();
        },
        onError: (err) => setError(errorMessage(err, 'The upload was not accepted. Try again.')),
      },
    );
  };

  const nextCode = hosted ? String(hosted.version_code + 1) : '12';
  return (
    <Dialog
      open={open}
      onClose={() => !busy && onClose()}
      title="Upload a new version"
      className="w-[520px]"
      actions={
        <>
          <Button variant="text" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="apk-upload-form" loading={busy}>
            Upload
          </Button>
        </>
      }
    >
      <p>Phones update from here on their next check.</p>
      <form id="apk-upload-form" onSubmit={submit} className="mt-4 flex flex-col gap-4" noValidate>
        <FilePicker
          label="APK file"
          accept=".apk"
          file={file}
          onChange={(f) => {
            setFile(f);
            setError(null);
          }}
          helper={file ? fmtSize(file.size) : undefined}
          disabled={busy}
        />
        <div className="flex flex-wrap gap-3">
          <TextField
            label="Version code"
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            placeholder={nextCode}
            value={versionCode}
            onChange={(e) => {
              setVersionCode(e.target.value);
              setError(null);
            }}
            disabled={busy}
            className="min-w-[120px] flex-1"
          />
          <TextField
            label="Version name"
            placeholder="1.2.0"
            maxLength={VERSION_NAME_MAX}
            value={versionName}
            onChange={(e) => {
              setVersionName(e.target.value);
              setError(null);
            }}
            disabled={busy}
            autoComplete="off"
            className="min-w-[160px] flex-[2]"
          />
          <TextField
            label="Minimum Android API level (optional)"
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            placeholder={hosted?.min_sdk ? String(hosted.min_sdk) : '26'}
            value={minSdk}
            onChange={(e) => {
              setMinSdk(e.target.value);
              setError(null);
            }}
            disabled={busy}
            className="min-w-[200px] flex-1"
          />
        </div>
        <TextField
          multiline
          label="Release notes (optional)"
          maxLength={NOTES_MAX}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={busy}
          className="[&_textarea]:min-h-[72px]"
        />
        {busy && (
          <LinearProgress
            value={progress}
            label={progress == null ? 'Uploading' : `Uploading, ${Math.round(progress * 100)}%`}
          />
        )}
        {error && (
          <div role="alert" className="text-body-s text-error">
            {error}
          </div>
        )}
      </form>
    </Dialog>
  );
}
