import { useState } from 'react';
import { Button } from '@/components/Button';
import { CopyField } from '@/components/CopyField';
import { ConfirmDialog } from '@/components/Dialog';
import { IconButton } from '@/components/IconButton';
import { Icon } from '@/components/Icon';
import { Skeleton } from '@/components/Skeleton';
import { useSnackbar } from '@/components/Snackbar';
import { errorMessage } from '@/api/client';
import { fetchApkBlob, useApkInfo, useDeleteApk } from '@/api/hooks/apk';
import { downloadBlob } from '@/features/shell/bridge';
import { fmtSize, fmtWhen } from '@/lib/format';
import { SettingsRow, SettingsSection } from '../SettingsSection';
import { ApkUploadDialog } from './ApkUploadDialog';

/**
 * Android app hosting: what is hosted now (version, size, upload time, notes) with Download, Copy
 * checksum and Remove; plus "Upload a new version". Nothing hosted shows an empty row and the
 * upload row.
 */
export function AndroidAppSection() {
  const query = useApkInfo();
  const del = useDeleteApk();
  const snackbar = useSnackbar();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const info = query.data ?? null;

  const download = async () => {
    setDownloading(true);
    try {
      const { blob, filename } = await fetchApkBlob();
      downloadBlob(blob, info?.filename || filename);
    } catch (e) {
      snackbar.error(errorMessage(e, "Couldn't download the app."));
    } finally {
      setDownloading(false);
    }
  };

  const remove = () => {
    del.mutate(undefined, {
      onSuccess: () => snackbar.show('App removed'),
      onError: (e) => snackbar.error(errorMessage(e, "Couldn't remove the app.")),
      onSettled: () => setConfirmRemove(false),
    });
  };

  return (
    <SettingsSection
      title="Android app"
      card
      actions={
        <IconButton
          icon="refresh"
          label="Refresh app info"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        />
      }
    >
      {query.isPending ? (
        <div className="flex items-center gap-4 py-3.5" aria-busy="true" aria-label="Loading app info">
          <Skeleton width={40} height={40} />
          <div className="flex-1">
            <Skeleton width="35%" height={14} className="my-[5px]" />
            <Skeleton width="55%" height={12} className="my-1" />
          </div>
        </div>
      ) : query.isError && query.data === undefined ? (
        <div className="flex flex-wrap items-center gap-3 py-3.5">
          <span className="flex-1 text-body-m text-error">
            {errorMessage(query.error, "Couldn't load the app info.")}
          </span>
          <Button variant="outlined" size="sm" icon="refresh" onClick={() => void query.refetch()}>
            Retry
          </Button>
        </div>
      ) : info ? (
        <SettingsRow
          icon="android"
          alignTop
          headline={
            <>
              Version {info.version_name}{' '}
              <span className="text-on-surface-variant">(build {info.version_code})</span>
            </>
          }
          supporting={`${fmtSize(info.size_bytes)} · uploaded ${fmtWhen(info.uploaded_at)}`}
        >
          {info.notes && (
            <div className="mt-2 whitespace-pre-wrap text-body-m text-on-surface-body">{info.notes}</div>
          )}
          <CopyField label="Checksum" value={info.sha256} copiedMessage="Checksum copied" className="mt-3" />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              variant="outlined"
              size="sm"
              icon="download"
              loading={downloading}
              onClick={() => void download()}
            >
              Download APK
            </Button>
            <Button
              variant="danger"
              size="sm"
              className="ml-auto"
              disabled={del.isPending}
              onClick={() => setConfirmRemove(true)}
            >
              Remove
            </Button>
          </div>
        </SettingsRow>
      ) : (
        <SettingsRow
          icon="android"
          headline="No app hosted yet"
          supporting="Upload one and phones can install it from here."
        />
      )}
      <SettingsRow
        icon="upload"
        headline="Upload a new version"
        supporting="Phones update from here on their next check."
        trailing={<Icon name="chevron_right" size={22} className="text-on-surface-variant" />}
        onClick={() => setUploadOpen(true)}
        aria-label="Upload a new version"
      />
      <ApkUploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} hosted={info} />
      <ConfirmDialog
        open={confirmRemove}
        danger
        title="Stop hosting the app?"
        ok="Remove"
        busy={del.isPending}
        onConfirm={remove}
        onCancel={() => !del.isPending && setConfirmRemove(false)}
      >
        <p>Phones won't be able to install or update from here until you upload a new version.</p>
      </ConfirmDialog>
    </SettingsSection>
  );
}
