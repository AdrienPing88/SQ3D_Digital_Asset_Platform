import { useEffect, useRef } from 'react';
import { useUploadStore } from '../store/uploadStore';
import { presignUpload, confirmUpload } from '../api/assets';
import { useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

async function computeSHA256(file: File): Promise<string> {
  try {
    const buffer = await file.arrayBuffer();
    const hash = await crypto.subtle.digest('SHA-256', buffer);
    return Array.from(new Uint8Array(hash))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    // Fallback for very large files that exhaust memory
    return '0'.repeat(64);
  }
}

async function processUpload(
  file: File,
  index: number,
  projectId: string,
  updateItem: (index: number, patch: any) => void,
  onComplete: () => void,
) {
  try {
    // 1. Hash
    updateItem(index, { status: 'uploading', progressPercent: 5 });
    const checksum = await computeSHA256(file);
    updateItem(index, { progressPercent: 15 });

    // 2. Presign
    const presign = await presignUpload(projectId, {
      filename: file.name,
      file_size_bytes: file.size,
      checksum_sha256: checksum,
      content_type: file.type || 'application/octet-stream',
    });
    updateItem(index, { assetId: presign.asset_id, progressPercent: 25 });

    // 3. Upload to storage (proxy through Vite to avoid CORS / IPv6 issues)
    const formData = new FormData();
    for (const [key, value] of Object.entries(presign.upload_fields)) {
      formData.append(key, value);
    }
    formData.append('file', file);

    // Rewrite MinIO URL to go through the /s3 Vite proxy
    let uploadUrl = presign.upload_url;
    try {
      const parsed = new URL(uploadUrl);
      uploadUrl = '/s3' + parsed.pathname + parsed.search;
    } catch {
      // If URL parsing fails, use as-is
    }

    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = 25 + Math.round((e.loaded / e.total) * 60);
          updateItem(index, { progressPercent: pct });
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`Storage upload failed (HTTP ${xhr.status}): ${xhr.responseText}`));
      };
      xhr.onerror = () => reject(new Error('Network error uploading to storage'));
      xhr.ontimeout = () => reject(new Error('Upload timed out'));
      xhr.open('POST', uploadUrl);
      xhr.send(formData);
    });

    // 4. Confirm
    updateItem(index, { status: 'confirming', progressPercent: 90 });
    await confirmUpload(projectId, presign.asset_id);
    updateItem(index, { status: 'complete', progressPercent: 100 });

    onComplete();
    toast.success(`${file.name} uploaded`);
  } catch (err: any) {
    const message = err?.response?.data?.detail || err?.message || 'Upload failed';
    updateItem(index, { status: 'error', error: message });
    toast.error(`Failed: ${file.name} — ${message}`);
  }
}

export function useUploadQueue(projectId: string) {
  const queryClient = useQueryClient();
  const activeFiles = useRef<WeakSet<File>>(new WeakSet());

  useEffect(() => {
    const { items, updateItem } = useUploadStore.getState();

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.status !== 'queued' || activeFiles.current.has(item.file)) continue;
      activeFiles.current.add(item.file);

      processUpload(item.file, i, projectId, updateItem, () => {
        queryClient.invalidateQueries({ queryKey: ['assets', projectId] });
      });
    }
  });

  // Also subscribe to store changes outside of React render cycle
  useEffect(() => {
    const unsub = useUploadStore.subscribe((state) => {
      const { items, updateItem } = state;
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.status !== 'queued' || activeFiles.current.has(item.file)) continue;
        activeFiles.current.add(item.file);

        processUpload(item.file, i, projectId, updateItem, () => {
          queryClient.invalidateQueries({ queryKey: ['assets', projectId] });
        });
      }
    });
    return unsub;
  }, [projectId, queryClient]);
}
