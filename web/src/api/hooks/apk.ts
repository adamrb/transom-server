import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, apiJson, apiRequest, AUTH_REQUIRED_EVENT, NetworkError } from '../client';
import { qk } from '../keys';
import { tokenStore } from '../token';
import { ApkInfoSchema, type ApkInfo, type ApkMetadata } from '../types';

/**
 * The hosted Android app. 404 means none is hosted: the hook returns `data: null` rather than an
 * error so Settings can show "No app hosted yet".
 */
export function useApkInfo() {
  return useQuery({
    queryKey: qk.apk,
    queryFn: async (): Promise<ApkInfo | null> => {
      try {
        return await apiJson('/apk/info', ApkInfoSchema);
      } catch (e) {
        if (e instanceof ApiError && e.notFound) return null;
        throw e;
      }
    },
  });
}

/** The APK download URL; the browser needs the bearer header, so fetch it as a blob. */
export async function fetchApkBlob(): Promise<{ blob: Blob; filename: string }> {
  const r = await apiRequest('/apk/file');
  const cd = r.headers.get('content-disposition') ?? '';
  const m = cd.match(/filename="([^"]+)"/i);
  return { blob: await r.blob(), filename: m?.[1] ?? 'plaud-bridge.apk' };
}

export interface UploadApkArgs {
  file: File;
  metadata: ApkMetadata;
  /** 0..1 */
  onProgress?: (fraction: number) => void;
}

/**
 * Upload a new APK with progress (XHR, since fetch has no upload progress). Errors carry the
 * server's sentence like every other request.
 */
export function uploadApk({ file, metadata, onProgress }: UploadApkArgs): Promise<ApkInfo> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('metadata', JSON.stringify(metadata));
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/apk');
    const t = tokenStore.get();
    if (t) xhr.setRequestHeader('Authorization', `Bearer ${t}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new NetworkError());
    xhr.onload = () => {
      if (xhr.status === 401) {
        window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
        reject(new ApiError(401, null, 'Please sign in again.'));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        const parsed = ApkInfoSchema.safeParse(JSON.parse(xhr.responseText));
        if (parsed.success) resolve(parsed.data);
        else reject(new ApiError(0, null, 'Your server answered in a way this app did not expect.'));
        return;
      }
      let detail: string | null = null;
      if (xhr.status < 500) {
        try {
          const d = JSON.parse(xhr.responseText)?.detail;
          detail = typeof d === 'string' ? d.slice(0, 300) : null;
        } catch {
          /* not JSON */
        }
      }
      reject(new ApiError(xhr.status, detail, 'The upload was not accepted. Try again.'));
    };
    xhr.send(fd);
  });
}

export function useUploadApk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: uploadApk,
    onSuccess: (info) => qc.setQueryData(qk.apk, info),
  });
}

/** Stop hosting the current APK (confirm first). */
export function useDeleteApk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiRequest('/apk', { method: 'DELETE' });
    },
    onSuccess: () => qc.setQueryData(qk.apk, null),
  });
}
