import api from './client';
import type { User } from '../types';

interface LoginRequest {
  email: string;
  password: string;
}

interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
  org_name?: string;
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export async function login(data: LoginRequest): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>('/v1/auth/login', data);
  return res.data;
}

export async function register(data: RegisterRequest): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>('/v1/auth/register', data);
  return res.data;
}

export async function getMe(): Promise<User> {
  const res = await api.get<User>('/v1/auth/me');
  return res.data;
}

export async function logout(): Promise<void> {
  await api.post('/v1/auth/logout');
}

// ── OAuth2 PKCE ─────────────────────────

interface OAuthAuthorizeResponse {
  authorization_url: string;
  state: string;
}

export async function startOAuthFlow(provider: 'google' | 'microsoft'): Promise<void> {
  const res = await api.get<OAuthAuthorizeResponse>(`/v1/auth/oauth/${provider}/authorize`);
  window.location.href = res.data.authorization_url;
}

export async function handleOAuthCallback(
  provider: 'google' | 'microsoft',
  code: string,
  state: string,
): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>(`/v1/auth/oauth/${provider}/callback`, { code, state });
  return res.data;
}

// ── Member Management ───────────────────

export interface ProjectMember {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
}

export async function getProjectMembers(projectId: string): Promise<ProjectMember[]> {
  const res = await api.get<ProjectMember[]>(`/v1/projects/${projectId}/members`);
  return res.data;
}

export async function inviteProjectMember(
  projectId: string,
  email: string,
  role: string,
): Promise<void> {
  await api.post(`/v1/projects/${projectId}/members`, { email, role });
}

export async function removeProjectMember(projectId: string, userId: string): Promise<void> {
  await api.delete(`/v1/projects/${projectId}/members/${userId}`);
}
