import { Link } from 'react-router-dom';
import { FolderOpen, Users, FileStack } from 'lucide-react';
import type { Project } from '../../types';
import { formatRelativeTime } from '../../utils/format';

interface Props {
  project: Project;
}

export default function ProjectCard({ project }: Props) {
  return (
    <Link
      to={`/projects/${project.id}`}
      className="group block rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-brand-300 hover:shadow-md"
    >
      <div className="mb-3 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 group-hover:bg-brand-100">
            <FolderOpen className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 group-hover:text-brand-700">
              {project.name}
            </h3>
            {project.description && (
              <p className="mt-0.5 text-sm text-gray-500 line-clamp-1">
                {project.description}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <FileStack className="h-3.5 w-3.5" />
          {project.asset_count} assets
        </span>
        <span className="flex items-center gap-1">
          <Users className="h-3.5 w-3.5" />
          {project.member_count} members
        </span>
        <span className="ml-auto">Updated {formatRelativeTime(project.updated_at)}</span>
      </div>
    </Link>
  );
}
