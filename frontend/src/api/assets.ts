import api from './client';
import type { Asset, PaginatedResponse, PresignResponse } from '../types';

export async function listAssets(
  projectId: string,
  params?: { page?: number; page_size?: number; asset_type?: string; status?: string },
): Promise<PaginatedResponse<Asset>> {
  const res = await api.get(`/v1/projects/${projectId}/assets`, { params });
  return res.data;
}

export async function getAsset(assetId: string): Promise<Asset> {
  const res = await api.get(`/v1/assets/${assetId}`);
  return res.data;
}

export async function presignUpload(
  projectId: string,
  data: { filename: string; file_size_bytes: number; checksum_sha256: string; content_type?: string },
): Promise<PresignResponse> {
  const res = await api.post(`/v1/projects/${projectId}/assets/presign`, data);
  return res.data;
}

export async function confirmUpload(
  projectId: string,
  assetId: string,
): Promise<Asset> {
  const res = await api.post(`/v1/projects/${projectId}/assets/confirm`, {}, { params: { asset_id: assetId } });
  return res.data;
}

export async function getDownloadUrl(assetId: string): Promise<string> {
  const res = await api.get(`/v1/assets/${assetId}/download`);
  return res.data.download_url;
}

export async function getStreamUrl(assetId: string): Promise<string> {
  const res = await api.get(`/v1/assets/${assetId}/stream`);
  return res.data.stream_url;
}

export async function deleteAsset(assetId: string): Promise<void> {
  await api.delete(`/v1/assets/${assetId}`);
}
