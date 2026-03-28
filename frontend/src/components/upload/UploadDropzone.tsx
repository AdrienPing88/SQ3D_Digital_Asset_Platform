import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload } from 'lucide-react';
import { useUploadStore } from '../../store/uploadStore';

export default function UploadDropzone() {
  const addFiles = useUploadStore((s) => s.addFiles);

  const onDrop = useCallback(
    (accepted: File[]) => {
      addFiles(accepted);
    },
    [addFiles],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
  });

  return (
    <div
      {...getRootProps()}
      className={`cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition ${
        isDragActive
          ? 'border-brand-400 bg-brand-50'
          : 'border-gray-300 hover:border-brand-300 hover:bg-gray-50'
      }`}
    >
      <input {...getInputProps()} />
      <Upload className="mx-auto mb-3 h-8 w-8 text-gray-400" />
      <p className="text-sm font-medium text-gray-600">
        {isDragActive ? 'Drop files here' : 'Drag & drop files, or click to browse'}
      </p>
      <p className="mt-1 text-xs text-gray-400">
        Supports point clouds, 3D models, drawings, imagery, and more
      </p>
    </div>
  );
}
