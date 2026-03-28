import { create } from 'zustand';
import type { UploadItem, UploadStatus } from '../types';

interface UploadState {
  items: UploadItem[];
  addFiles: (files: File[]) => void;
  updateItem: (index: number, patch: Partial<UploadItem>) => void;
  removeItem: (index: number) => void;
  clearCompleted: () => void;
}

export const useUploadStore = create<UploadState>((set) => ({
  items: [],
  addFiles: (files) =>
    set((state) => ({
      items: [
        ...state.items,
        ...files.map((file) => ({
          file,
          status: 'queued' as UploadStatus,
          progressPercent: 0,
        })),
      ],
    })),
  updateItem: (index, patch) =>
    set((state) => ({
      items: state.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    })),
  removeItem: (index) =>
    set((state) => ({
      items: state.items.filter((_, i) => i !== index),
    })),
  clearCompleted: () =>
    set((state) => ({
      items: state.items.filter((item) => item.status !== 'complete'),
    })),
}));
