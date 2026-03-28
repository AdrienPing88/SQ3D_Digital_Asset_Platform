import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, FileStack, Eye, Pencil, Trash2, Users, UserPlus, X } from 'lucide-react';
import { useProject } from '../hooks/useProjects';
import { useAssets } from '../hooks/useAssets';
import { useUploadQueue } from '../hooks/useUploadQueue';
import UploadDropzone from '../components/upload/UploadDropzone';
import UploadProgress from '../components/upload/UploadProgress';
import EditProjectModal from '../components/dashboard/EditProjectModal';
import DeleteProjectModal from '../components/dashboard/DeleteProjectModal';
import { formatBytes, formatRelativeTime, assetTypeLabel, statusBadgeClass } from '../utils/format';
import { getProjectMembers, inviteProjectMember, removeProjectMember } from '../api/auth';
import type { ProjectMember } from '../api/auth';

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { data: project, isLoading: loadingProject } = useProject(projectId!);
  const { data: assetsData, isLoading: loadingAssets } = useAssets(projectId!);
  const [showUpload, setShowUpload] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [showMembers, setShowMembers] = useState(false);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('collaborator');
  useUploadQueue(projectId!);

  useEffect(() => {
    if (showMembers && projectId) {
      getProjectMembers(projectId).then(setMembers).catch(() => {});
    }
  }, [showMembers, projectId]);

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

      {/* Members panel */}
      <div className="mt-6 rounded-xl border border-gray-200 bg-white">
        <button
          onClick={() => setShowMembers(!showMembers)}
          className="flex w-full items-center justify-between px-5 py-3 text-left"
        >
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-700">
              Members ({project.member_count})
            </h2>
          </div>
          <span className="text-xs text-gray-400">{showMembers ? 'Hide' : 'Show'}</span>
        </button>

        {showMembers && (
          <div className="border-t border-gray-100 px-5 py-4">
            {/* Invite form */}
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                if (!inviteEmail || !projectId) return;
                await inviteProjectMember(projectId, inviteEmail, inviteRole);
                setInviteEmail('');
                const updated = await getProjectMembers(projectId);
                setMembers(updated);
              }}
              className="mb-4 flex items-center gap-2"
            >
              <UserPlus className="h-4 w-4 text-gray-400" />
              <input
                type="email"
                placeholder="Email address"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
              >
                <option value="viewer">Viewer</option>
                <option value="collaborator">Collaborator</option>
                <option value="admin">Admin</option>
              </select>
              <button
                type="submit"
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                Invite
              </button>
            </form>

            {/* Member list */}
            {members.length === 0 ? (
              <p className="text-sm text-gray-400">No members yet</p>
            ) : (
              <ul className="divide-y divide-gray-50">
                {members.map((m) => (
                  <li key={m.user_id} className="flex items-center justify-between py-2">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-200 text-xs font-medium text-gray-600">
                        {m.display_name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900">{m.display_name}</p>
                        <p className="text-xs text-gray-400">{m.email}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                        {m.role}
                      </span>
                      <button
                        onClick={async () => {
                          if (!projectId) return;
                          await removeProjectMember(projectId, m.user_id);
                          setMembers((prev) => prev.filter((x) => x.user_id !== m.user_id));
                        }}
                        className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
                        title="Remove member"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
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
