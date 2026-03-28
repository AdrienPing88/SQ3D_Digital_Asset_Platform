// SQ3D Digital Asset Platform — Core TypeScript Types
// Property names match the snake_case API response format.

// ─────────────────────────────────────────
// Auth
// ─────────────────────────────────────────

export type GlobalRole = 'org_admin' | 'member';
export type ProjectRole = 'owner' | 'admin' | 'collaborator' | 'viewer';

export interface User {
  id: string;
  org_id: string;
  email: string;
  display_name: string;
  global_role: GlobalRole;
  avatar_url?: string;
  last_login?: string;
}

export interface AuthTokens {
  access_token: string;
  expires_at: string;
}

// ─────────────────────────────────────────
// Organization
// ─────────────────────────────────────────

export type OrgPlan = 'free' | 'pro' | 'enterprise';

export interface Organization {
  id: string;
  name: string;
  plan: OrgPlan;
  storage_quota_bytes: number;
  storage_used_bytes: number;
  settings: Record<string, unknown>;
  created_at: string;
}

// ─────────────────────────────────────────
// Projects
// ─────────────────────────────────────────

export interface Project {
  id: string;
  org_id: string;
  name: string;
  description?: string;
  bbox?: GeoJSONPolygon;
  coordinate_system: string;
  metadata: Record<string, unknown>;
  archived: boolean;
  asset_count: number;
  member_count: number;
  updated_at: string;
  created_at: string;
}

export interface ProjectMember {
  user_id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  role: ProjectRole;
  granted_at: string;
}

// ─────────────────────────────────────────
// Assets
// ─────────────────────────────────────────

export type AssetType =
  | 'las' | 'laz' | 'e57'
  | 'orthomosaic' | 'flight_log' | 'raw_imagery'
  | 'panorama_360' | 'panorama_video'
  | 'pdf' | 'dwg' | 'dxf' | 'rvt'
  | 'obj' | 'fbx' | 'ifc' | 'glb' | 'gltf'
  | 'geotiff' | 'geojson' | 'kml' | 'shp'
  | 'other';

export type AssetStatus = 'pending' | 'processing' | 'ready' | 'error' | 'archived';

export interface Asset {
  id: string;
  project_id: string;
  uploaded_by: string;
  name: string;
  asset_type: AssetType;
  file_size_bytes: number;
  status: AssetStatus;
  spatial_metadata: Record<string, unknown>;
  version: number;
  thumbnail_url?: string;
  tile_root_url?: string;
  annotation_count: number;
  created_at: string;
  updated_at: string;
}

// ─────────────────────────────────────────
// Upload
// ─────────────────────────────────────────

export interface PresignResponse {
  asset_id: string;
  upload_url: string;
  upload_fields: Record<string, string>;
  storage_key: string;
  expires_in: number;
}

export type UploadStatus = 'queued' | 'uploading' | 'confirming' | 'processing' | 'complete' | 'error';

export interface UploadItem {
  file: File;
  assetId?: string;
  status: UploadStatus;
  progressPercent: number;
  error?: string;
}

// ─────────────────────────────────────────
// Annotations
// ─────────────────────────────────────────

export type AnnotationType = 'note' | 'issue' | 'measurement' | 'approval' | 'markup';

export interface AnnotationPosition {
  x: number;
  y: number;
  z: number;
  normal?: [number, number, number];
  camera_pose?: CameraPose;
  page_number?: number;
}

export interface CameraPose {
  position: [number, number, number];
  target: [number, number, number];
  up: [number, number, number];
}

export interface Annotation {
  id: string;
  asset_id: string;
  created_by: string;
  creator_name: string;
  annotation_type: AnnotationType;
  position_data: AnnotationPosition;
  content?: string;
  resolved: boolean;
  resolved_by?: string;
  resolved_at?: string;
  comment_count: number;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: string;
  annotation_id: string;
  author_id: string;
  author_name: string;
  content: string;
  edited: boolean;
  created_at: string;
}

// ─────────────────────────────────────────
// Real-time / WebSocket
// ─────────────────────────────────────────

export type WSEventType =
  | 'annotation.created'
  | 'annotation.updated'
  | 'annotation.resolved'
  | 'comment.added'
  | 'asset.processing_update'
  | 'asset.processing_complete'
  | 'user.joined'
  | 'user.left'
  | 'cursor.moved';

export interface WSEvent<T = unknown> {
  type: WSEventType;
  payload: T;
}

export interface CollaboratorPresence {
  user_id: string;
  display_name: string;
  avatar_url?: string;
  cursor_position?: AnnotationPosition;
  color: string;
}

// ─────────────────────────────────────────
// Sharing
// ─────────────────────────────────────────

export type SharePermission = 'view' | 'comment' | 'download';

export interface SharingLink {
  id: string;
  token: string;
  permission_level: SharePermission;
  expires_at?: string;
  access_count: number;
  max_access_count?: number;
  active: boolean;
  created_at: string;
}

// ─────────────────────────────────────────
// Misc
// ─────────────────────────────────────────

export interface GeoJSONPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}
