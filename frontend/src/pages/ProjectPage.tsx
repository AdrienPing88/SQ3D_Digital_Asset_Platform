import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, FileStack, Eye, Pencil, Trash2 } from 'lucide-react';
import { useProject } from '../hooks/useProjects';
import { useAssets } from '../hooks/useAssets';
import { useUploadQueue } from '../hooks/useUploadQueue';
import UploadDropzone from '../components/upload/UploadDropzone';
import UploadProgress from '../components/upload/UploadProgress';
import EditProjectModal from '../components/dashboard/EditProjectModal';
import DeleteProjectModal from '../components/dashboard/DeleteProjectModal';
import { formatBytes, formatRelativeTime, assetTypeLabel, statusBadgeClass } from '../utils/format';

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { data: project, isLoading: loadingProject } = useProject(projectId!);
  const { data: assetsData, isLoading: loadingAssets } = useAssets(projectId!);
  const [showUpload, setShowUpload] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  useUploadQueue(projectId!);

  if (loadingProject) {
    return <div className="py-20 text-center text-gray-400">Loading...</div>;
  }
  if (!project) {
    return <div className="py-20 text-center text-gray-500">Project not found</div>;
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <Link to="/" className="mb-2 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-4 w-4" />
          All projects
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
            {project.description && (
              <p className="mt-1 text-sm text-gray-500">{project.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEdit(true)}
              className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <Pencil className="h-4 w-4" />
              Edit
            </button>
            <button
              onClick={() => setShowDelete(true)}
              className="flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
            <button
              onClick={() => setShowUpload(!showUpload)}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700"
            >
              <FileStack className="h-4 w-4" />
              Upload Assets
            </button>
          </div>
        </div>
      </div>

      {/* Upload area */}
      {showUpload && (
        <div className="mb-6">
          <UploadDropzone />
          <UploadProgress />
        </div>
      )}

      {/* Asset list */}
      <div className="rounded-xl border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-5 py-3">
          <h2 className="text-sm font-semibold text-gray-700">
            Assets ({assetsData?.total ?? 0})
          </h2>
        </div>

        {loadingAssets ? (
          <div className="py-12 text-center text-gray-400">Loading assets...</div>
        ) : !assetsData?.items.length ? (
          <div className="py-12 text-center text-gray-400">
            <p>No assets uploaded yet</p>
            <button
              onClick={() => setShowUpload(true)}
              className="mt-2 text-sm font-medium text-brand-600 hover:text-brand-700"
            >
              Upload your first asset
            </button>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase tracking-wider text-gray-400">
                <th className="px-5 py-3">Name</th>
                <th className="px-5 py-3">Type</th>
                <th className="px-5 py-3">Size</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Uploaded</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {assetsData.items.map((asset) => (
                <tr key={asset.id} className="hover:bg-gray-50">
                  <td className="px-5 py-3">
                    <Link
                      to={`/assets/${asset.id}`}
                      className="text-sm font-medium text-gray-900 hover:text-brand-600"
                    >
                      {asset.name}
                    </Link>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-500">
                    {assetTypeLabel(asset.asset_type)}
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-500">
                    {formatBytes(asset.file_size_bytes)}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(asset.status)}`}
                    >
                      {asset.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">
                    {formatRelativeTime(asset.created_at)}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-1">
                      <Link
                        to={`/assets/${asset.id}`}
                        className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                        title="View"
                      >
                        <Eye className="h-4 w-4" />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      <EditProjectModal
        open={showEdit}
        onClose={() => setShowEdit(false)}
        project={project}
      />
      <DeleteProjectModal
        open={showDelete}
        onClose={() => setShowDelete(false)}
        project={project}
        onDeleted={() => navigate('/')}
      />
    </div>
  );
}
