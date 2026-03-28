import { X, AlertTriangle } from 'lucide-react';
import { useDeleteProject } from '../../hooks/useProjects';
import type { Project } from '../../types';

interface Props {
  open: boolean;
  onClose: () => void;
  project: Project;
  onDeleted: () => void;
}

export default function DeleteProjectModal({ open, onClose, project, onDeleted }: Props) {
  const deleteProject = useDeleteProject();

  if (!open) return null;

  const handleDelete = () => {
    deleteProject.mutate(project.id, {
      onSuccess: () => {
        onClose();
        onDeleted();
      },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Delete Project</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-gray-100">
            <X className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        <div className="mb-5 flex items-start gap-3 rounded-lg bg-red-50 p-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
          <div className="text-sm text-red-700">
            <p className="font-medium">This will archive "{project.name}"</p>
            <p className="mt-1 text-red-600">
              All assets and data within this project will be archived.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={deleteProject.isPending}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          >
            {deleteProject.isPending ? 'Deleting...' : 'Delete project'}
          </button>
        </div>
      </div>
    </div>
  );
}
