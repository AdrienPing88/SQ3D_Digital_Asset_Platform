# Architecture Decision Record — SQ3D Digital Asset Platform

**Version:** 0.1 (MVP)  
**Status:** In Design  
**Last Updated:** 2026-03-25

---

## 1. System Architecture

### Tier Overview

```
┌─────────────────────────────────────────────────────────┐
│  CLIENT TIER                                            │
│  React 18 PWA  ·  Potree.js  ·  Three.js  ·  Cesium   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS / WSS
┌────────────────────────▼────────────────────────────────┐
│  CDN / EDGE                                             │
│  CloudFront  ·  Static assets  ·  Tile streaming        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  API GATEWAY                                            │
│  Kong / AWS API Gateway  ·  Rate limiting  ·  Routing  │
└──┬──────────────┬──────────────┬──────────────┬─────────┘
   │              │              │              │
┌──▼───┐  ┌──────▼──┐  ┌───────▼──┐  ┌───────▼──────┐
│ Auth │  │  Asset  │  │  Collab  │  │  Job Worker  │
│ svc  │  │  svc    │  │  svc     │  │  (Celery)    │
└──┬───┘  └──┬──────┘  └───┬──────┘  └───────┬──────┘
   │         │             │                  │
┌──▼─────────▼─────────────▼──────────────────▼─────────┐
│  DATA TIER                                             │
│  PostgreSQL+PostGIS  ·  Redis  ·  S3  ·  Elasticsearch│
└────────────────────────────────────────────────────────┘
```

### Why FastAPI over Node.js

FastAPI's async def endpoints handle concurrent large-file streaming without blocking. Python's scientific stack integrates natively: PDAL (point cloud tiling), rasterio (orthomosaic projection), ifcopenshell (BIM parsing), numpy for spatial transforms. Pydantic enforces strict validation on complex geospatial metadata schemas at the API boundary.

### Why S3 Direct Upload (Presigned URLs)

A 50 GB LAZ file passing through the API server would require:
- 50 GB RAM headroom per concurrent upload
- Linear upload latency through the API tier
- Impossible horizontal scaling for the API pods

With presigned URLs, the API server generates a signed S3 URL (valid 6h), the client uploads directly to S3 over Transfer Acceleration, and S3 emits an ObjectCreated event to SQS when the upload completes. API servers never touch binary data.

### Why Potree.js for Point Cloud Rendering

Point clouds from LiDAR surveys routinely exceed 500M points (5–100 GB as LAZ). Loading this into WebGL memory is impossible. Potree.js implements an LOD octree: the tile converter (run on ingest) partitions the cloud into a hierarchical tree of ~150,000-point chunks. The browser streams only the chunks visible at the current camera zoom level, targeting 1M points in GPU memory at any time. This allows smooth navigation of arbitrarily large clouds in-browser.

### Why PostGIS + PostgreSQL over a pure document store

- Spatial R-tree index on project bounding boxes enables `ST_Intersects` queries (find all projects overlapping a given region)
- Row-Level Security policies enforce org isolation at the database layer, independent of application logic
- JSONB provides schema-flexible asset metadata without sacrificing ACID transactions
- Foreign key integrity prevents orphaned assets if a project is deleted

---

## 2. Database Schema (DDL)

See `database/migrations/001_initial_schema.sql` for the full Alembic migration.

### Core Tables

```sql
-- organizations: top-level billing and permission boundary
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free','pro','enterprise')),
    storage_quota_bytes BIGINT NOT NULL DEFAULT 107374182400, -- 100 GB default
    storage_used_bytes BIGINT NOT NULL DEFAULT 0,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- users: scoped to an org
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT,                    -- null for SSO-only accounts
    global_role TEXT NOT NULL DEFAULT 'member' CHECK (global_role IN ('org_admin','member')),
    mfa_secret TEXT,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- projects: geospatial project container
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT,
    bbox GEOMETRY(Polygon, 4326),            -- WGS84 bounding box for spatial queries
    coordinate_system TEXT DEFAULT 'EPSG:4326',
    metadata JSONB NOT NULL DEFAULT '{}',
    archived BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_projects_bbox ON projects USING GIST(bbox);

-- assets: every uploaded file
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN (
        'las','laz','e57',
        'orthomosaic','flight_log','raw_imagery',
        'panorama_360','panorama_video',
        'pdf','dwg','dxf','rvt',
        'obj','fbx','ifc','glb','gltf',
        'geotiff','geojson','kml','shp','other'
    )),
    storage_key TEXT NOT NULL UNIQUE,        -- S3 object key
    storage_bucket TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending','processing','ready','error','archived'
    )),
    spatial_metadata JSONB NOT NULL DEFAULT '{}',  -- CRS, bbox, point_count, density, etc.
    version INT NOT NULL DEFAULT 1,
    parent_asset_id UUID REFERENCES assets(id),    -- for versioning
    tile_root_key TEXT,                            -- S3 key for Potree tile root
    thumbnail_key TEXT,                            -- S3 key for preview image
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_assets_project ON assets(project_id);
CREATE INDEX idx_assets_type ON assets(asset_type);

-- project_permissions: role assignments
CREATE TABLE project_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner','admin','collaborator','viewer')),
    granted_by UUID REFERENCES users(id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, user_id)
);

-- annotations: spatial pins on assets
CREATE TABLE annotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    annotation_type TEXT NOT NULL CHECK (annotation_type IN (
        'note','issue','measurement','approval','markup'
    )),
    position_data JSONB NOT NULL,   -- {x,y,z,normal,camera_pose,page_number}
    content TEXT,
    resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- comments: threaded replies on annotations
CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    annotation_id UUID NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    edited BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- processing_jobs: async processing pipeline state
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (job_type IN (
        'tile_point_cloud','generate_thumbnail','extract_metadata',
        'reproject','validate_format','convert_to_glb'
    )),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued','running','complete','failed','cancelled'
    )),
    progress_pct INT NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    celery_task_id TEXT,
    error_message TEXT,
    output_metadata JSONB DEFAULT '{}',
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- sharing_links: external access tokens
CREATE TABLE sharing_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    token TEXT NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
    permission_level TEXT NOT NULL CHECK (permission_level IN ('view','comment','download')),
    password_hash TEXT,                          -- optional password protection
    expires_at TIMESTAMPTZ,
    access_count INT NOT NULL DEFAULT 0,
    max_access_count INT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (asset_id IS NOT NULL OR project_id IS NOT NULL)
);
```

---

## 3. API Endpoints

Base: `https://api.sq3d.io/v1`

### Authentication
| Method | Path | Description |
|---|---|---|
| POST | /auth/login | Email + password → JWT + refresh cookie |
| POST | /auth/refresh | Rotate access token using refresh cookie |
| POST | /auth/logout | Revoke refresh token |
| GET | /auth/sso/{provider} | Initiate PKCE OAuth (google, microsoft) |
| GET | /auth/sso/callback | OAuth callback handler |
| POST | /auth/ws-ticket | Issue 30-second WebSocket auth ticket |

### Projects
| Method | Path | Description |
|---|---|---|
| GET | /projects | List org projects (paginated, filterable) |
| POST | /projects | Create project |
| GET | /projects/{id} | Get project + member list |
| PATCH | /projects/{id} | Update name, description, bbox |
| DELETE | /projects/{id} | Soft-delete (archived=true) |
| GET | /projects/{id}/members | List members with roles |
| POST | /projects/{id}/members | Invite member by email |
| PATCH | /projects/{id}/members/{user_id} | Change role |
| DELETE | /projects/{id}/members/{user_id} | Remove member |
| POST | /projects/{id}/share | Create project sharing link |

### Assets
| Method | Path | Description |
|---|---|---|
| GET | /projects/{id}/assets | List assets (filterable by type, status) |
| POST | /projects/{id}/assets/presign | Get presigned S3 URL + create pending record |
| POST | /projects/{id}/assets/confirm | Confirm upload complete; trigger processing |
| GET | /assets/{id} | Asset detail + metadata |
| PATCH | /assets/{id} | Update name, metadata |
| DELETE | /assets/{id} | Move to trash |
| GET | /assets/{id}/stream | Get CloudFront signed tile URL (Potree) |
| GET | /assets/{id}/download | Get time-limited S3 download URL |
| POST | /assets/{id}/reprocess | Re-queue processing job |
| GET | /assets/{id}/versions | Version history |
| POST | /assets/{id}/share | Create asset sharing link |

### Annotations
| Method | Path | Description |
|---|---|---|
| GET | /assets/{id}/annotations | List (filterable by bbox, type, resolved) |
| POST | /assets/{id}/annotations | Create spatial annotation |
| PATCH | /annotations/{id} | Update content / resolve |
| DELETE | /annotations/{id} | Delete (creator or admin only) |
| POST | /annotations/{id}/comments | Reply to annotation |
| PATCH | /comments/{id} | Edit comment |

### Search
| Method | Path | Description |
|---|---|---|
| GET | /search | Full-text + spatial search across assets, annotations |

Query params: `q`, `project_id[]`, `type[]`, `status[]`, `date_from`, `date_to`, `bbox` (WKT)

### WebSocket Events
Endpoint: `wss://api.sq3d.io/ws/projects/{id}?ticket={ws_ticket}`

| Event (server → client) | Payload |
|---|---|
| `annotation.created` | Full annotation object |
| `annotation.updated` | Annotation id + diff |
| `annotation.resolved` | Annotation id + resolver |
| `comment.added` | Comment object + annotation_id |
| `asset.processing_update` | asset_id + status + progress_pct |
| `asset.processing_complete` | Full asset object |
| `user.joined` | user_id + display_name |
| `user.left` | user_id |
| `cursor.moved` | user_id + {x,y,z} position in asset space |

| Event (client → server) | Payload |
|---|---|
| `cursor.move` | {x,y,z} in asset coordinate space |
| `typing.start` | annotation_id |
| `typing.stop` | annotation_id |

---

## 4. Storage Architecture

### S3 Bucket Layout
```
sq3d-assets-{env}/
  orgs/{org_id}/
    projects/{project_id}/
      raw/
        {asset_id}/{original_filename}     ← original upload
      tiles/
        {asset_id}/cloud.js                ← Potree metadata root
        {asset_id}/data/                   ← LOD tile chunks
      thumbnails/
        {asset_id}/thumb.jpg
      previews/
        {asset_id}/page_{n}.jpg            ← PDF/DWG page previews
```

### Upload Flow (Step by Step)
1. Client calls `POST /assets/presign` with filename, size, type, checksum
2. API validates quota, creates `assets` record with `status='pending'`, returns presigned URL
3. Client uses S3 SDK to perform multipart upload in 100 MB chunks directly to S3
4. On completion, client calls `POST /assets/confirm` with ETag
5. S3 emits `ObjectCreated` event → SQS → Celery worker picks up the job
6. Worker validates checksum, runs format-specific processing, writes tile output
7. Worker updates `assets.status='ready'`, `assets.tile_root_key`, `assets.spatial_metadata`
8. Worker publishes `asset.processing_complete` to Redis pubsub → WebSocket broadcast

### Processing Workers by Asset Type
| Type | Worker Steps |
|---|---|
| LAZ / LAS / E57 | PDAL pipeline → validate CRS → filter noise → Potree tiler → write octree |
| Orthomosaic (GeoTIFF) | rasterio → validate CRS → generate COG → tile pyramid → thumbnail |
| IFC / RVT | ifcopenshell → parse elements → convert to GLB → Three.js-ready |
| DWG / DXF | ezdxf → parse layers → rasterize pages → export SVG per page |
| PDF | PyMuPDF → rasterize pages → full-text extract → Elasticsearch index |
| GLB / GLTF / OBJ | Three.js loader (headless) → validate → generate thumbnail |
| 360° equirect | PIL → validate aspect ratio → generate cubemap tiles |

---

## 5. Collaborative Features

### Real-time Annotations
- Annotations are created optimistically on the client, then confirmed via API
- On confirmation, the server broadcasts `annotation.created` to all project WebSocket connections
- Annotation pins render as floating 3D markers in Potree/Cesium and as overlay pins on PDF pages
- Position is stored in asset-local coordinates AND projected WGS84 coordinates where applicable

### Presence System
- On WS connect, server adds user to project room and broadcasts `user.joined`
- Clients emit `cursor.move` at 15 fps; server rate-limits to 10 fps per user before broadcast
- Each connected user's cursor appears as a colour-coded avatar in the 3D viewport
- Disconnect (or tab close) triggers `user.left` broadcast

### Sharing Links
- Links can be scoped to `view` (no annotations visible), `comment` (can add annotations), or `download`
- Optional password protection (bcrypt-hashed, checked server-side before issuing a short-lived session)
- Optional expiry date and max access count
- Recipient gets a read-only JWT issued on link access; their actions are attributed to "Guest via link"

---

## 6. Security Considerations

### Org Isolation
- PostgreSQL Row-Level Security on `assets`, `projects`, `annotations`, `comments` — every query automatically scoped to the caller's `org_id` via a session variable set on connection
- S3 paths include `org_id` as the top-level prefix; IAM policies restrict each backend service to its own prefix
- Cross-org data access is impossible even with a valid JWT if the `org_id` doesn't match

### Large File Security
- Presigned URLs are scoped to exact S3 key and expire in 6 hours
- SHA-256 checksum supplied at presign time; confirmed at `confirm` call and re-validated by the worker
- Uploaded files are scanned by ClamAV via the Celery pipeline before `status` is set to `ready`
- CloudFront streaming URLs are signed and expire in 1 hour; Potree requests new signed URLs via the API when tiles load

### Authentication
- JWT access tokens: 15-minute TTL, HS256, with `org_id`, `user_id`, `role` claims
- Refresh tokens: 30-day TTL, stored as HttpOnly + SameSite=Strict cookies
- MFA: TOTP (RFC 6238) enforced for org_admin accounts on enterprise plans
- SSO: PKCE flow for Google Workspace and Microsoft Entra; no client secret exposed to browser

### API Rate Limiting
- Kong rate limiting plugin: 100 req/min per user for standard endpoints
- Upload presign: 20 req/min per user
- WebSocket connections: 5 concurrent per user
