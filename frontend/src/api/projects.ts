import api from './client';
import type { Project, ProjectMember, PaginatedResponse } from '../types';

interface CreateProjectData {
  name: string;
  description?: string;
  coordinate_system?: string;
}

export async function listProjects(params?: {
  page?: number;
  page_size?: number;
  search?: string;
  archived?: boolean;
}): Promise<PaginatedResponse<Project>> {
  const res = await api.get('/v1/projects', { params });
  return res.data;
}

export async function getProject(id: string): Promise<Project> {
  const res = await api.get(`/v1/projects/${id}`);
  return res.data;
}

export async function createProject(data: CreateProjectData): Promise<Project> {
  const res = await api.post('/v1/projects', data);
  return res.data;
}

export async function updateProject(
  id: string,
  data: Partial<CreateProjectData & { archived: boolean }>,
): Promise<Project> {
  const res = await api.patch(`/v1/projects/${id}`, data);
  return res.data;
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/v1/projects/${id}`);
}

export async function listMembers(projectId: string): Promise<ProjectMember[]> {
  const res = await api.get(`/v1/projects/${projectId}/members`);
  return res.data;
}

export async function addMember(
  projectId: string,
  email: string,
  role: string = 'collaborator',
): Promise<ProjectMember> {
  const res = await api.post(`/v1/projects/${projectId}/members`, { email, role });
  return res.data;
}
