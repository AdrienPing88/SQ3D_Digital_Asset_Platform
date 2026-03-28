import { X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useUploadStore } from '../../store/uploadStore';
import { formatBytes } from '../../utils/format';

export default function UploadProgress() {
  const items = useUploadStore((s) => s.items);
  const removeItem = useUploadStore((s) => s.removeItem);
  const clearCompleted = useUploadStore((s) => s.clearCompleted);

  if (items.length === 0) return null;

  const completedCount = items.filter((i) => i.status === 'complete').length;

  return (
    <div className="mt-4 rounded-xl border border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <span className="text-sm font-medium text-gray-700">
          Uploads ({completedCount}/{items.length})
        </span>
        {completedCount > 0 && (
          <button
            onClick={clearCompleted}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Clear completed
          </button>
        )}
      </div>
      <ul className="max-h-60 divide-y divide-gray-50 overflow-y-auto">
        {items.map((item, i) => (
          <li key={i} className="flex items-center gap-3 px-4 py-2.5">
            {item.status === 'complete' ? (
              <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
            ) : item.status === 'error' ? (
              <AlertCircle className="h-4 w-4 shrink-0 text-red-500" />
            ) : item.status === 'uploading' || item.status === 'processing' ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-500" />
            ) : (
              <div className="h-4 w-4 shrink-0 rounded-full border-2 border-gray-200" />
            )}

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-gray-700">{item.file.name}</p>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">{formatBytes(item.file.size)}</span>
                {item.status === 'uploading' && (
                  <div className="h-1 flex-1 rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full bg-brand-500 transition-all"
                      style={{ width: `${item.progressPercent}%` }}
                    />
                  </div>
                )}
                {item.error && <span className="text-xs text-red-500">{item.error}</span>}
              </div>
            </div>

            <button onClick={() => removeItem(i)} className="shrink-0 p-1 hover:bg-gray-100 rounded">
              <X className="h-3.5 w-3.5 text-gray-400" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
