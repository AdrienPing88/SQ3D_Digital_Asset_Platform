# SQ3D Digital Asset Platform

A collaborative digital asset management (DAM) platform purpose-built for geospatial and construction data workflows. Supports point clouds, drone data, 360° imagery, BIM/CAD drawings, and 3D models with real-time collaboration, spatial annotations, and secure client-isolated storage.

---

## Project Structure

```
SQ3D Digital Asset Platform/
├── docs/                        # Architecture, API specs, design decisions
├── frontend/                    # React 18 + TypeScript (Vite)
│   └── src/
│       ├── components/
│       │   ├── viewer/          # Potree, Three.js, Cesium rendering
│       │   ├── upload/          # Multipart upload + progress
│       │   ├── dashboard/       # Project cards, stats
│       │   ├── annotations/     # Spatial pin UI, comment threads
│       │   ├── auth/            # Login, SSO, session
│       │   └── shared/          # Buttons, inputs, modals, nav
│       ├── pages/               # Route-level page components
│       ├── hooks/               # Custom React hooks
│       ├── store/               # Zustand global state
│       ├── utils/               # Helpers, format detection, coordinate utils
│       └── types/               # TypeScript interfaces and enums
├── backend/                     # Python FastAPI
│   └── app/
│       ├── api/v1/endpoints/    # Route handlers
│       ├── core/                # Config, security, dependencies
│       ├── models/              # SQLAlchemy ORM models
│       ├── schemas/             # Pydantic request/response schemas
│       ├── services/            # Business logic layer
│       ├── workers/             # Celery task definitions
│       └── utils/               # Spatial helpers, file parsers
├── database/
│   ├── migrations/              # Alembic migration files
│   └── seeds/                   # Dev/test seed data
├── infra/
│   ├── docker/                  # Dockerfiles per service
│   ├── k8s/                     # Kubernetes manifests
│   └── terraform/               # AWS infrastructure as code
└── .vscode/                     # Workspace settings and extensions
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript, Vite, Zustand, TanStack Query |
| 3D Rendering | Potree.js (point clouds), Three.js (3D models), Cesium.js (georef) |
| Backend API | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic |
| Task Queue | Celery 5 + Redis |
| Database | PostgreSQL 15 + PostGIS 3.4 |
| Cache / PubSub | Redis 7 |
| Object Storage | AWS S3 + CloudFront CDN |
| Search | Elasticsearch 8 |
| Real-time | Socket.io (WebSocket) |
| Infra | Docker, Kubernetes, Terraform |

---

## Quick Start

### Prerequisites
- Docker Desktop
- Node.js 20+
- Python 3.12+
- AWS CLI configured

### 1. Clone and configure
```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
# Edit both .env files with your credentials
```

### 2. Start local services
```bash
docker compose -f infra/docker/docker-compose.dev.yml up -d
```

### 3. Run database migrations
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.database.seeds.dev_seed
```

### 4. Start the backend
```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

App available at: http://localhost:5173  
API docs at: http://localhost:8000/docs

---

## Key Design Decisions

See `docs/architecture.md` for full rationale. Summary:

- **Direct-to-S3 upload** via presigned URLs — the API server never touches binary data for large files
- **Potree.js LOD streaming** — point clouds are tiled into octrees on ingest; the browser streams only visible nodes
- **PostGIS row-level security** — org isolation is enforced at the database level, not just the application layer
- **JSONB spatial metadata** — flexible per-format metadata without schema migrations
- **WebSocket presence** — real-time collaborator cursors and annotation sync via Socket.io rooms per project

---

## Supported Asset Types

| Category | Formats |
|---|---|
| Point clouds | `.las`, `.laz`, `.e57` |
| Drone data | Orthomosaics (GeoTIFF), flight logs (CSV/JSON), raw imagery (JPG/RAW) |
| 360° camera | Equirectangular JPG/PNG, panoramic MP4 |
| Design drawings | PDF, DWG, DXF, RVT |
| 3D models | `.obj`, `.fbx`, `.ifc`, `.glb`, `.gltf` |
| Geospatial | GeoTIFF, GeoJSON, KML, SHP |

---

## Roadmap

- [ ] MVP: Auth, upload, project management, basic viewer
- [ ] Potree point cloud viewer with spatial annotations
- [ ] IFC/BIM viewer with element selection
- [ ] Real-time collaboration (presence, annotations, comments)
- [ ] Sharing links with permission scopes
- [ ] Processing pipeline (tiling, thumbnail generation, metadata extraction)
- [ ] Mobile PWA for field upload
- [ ] Elasticsearch full-text + spatial search
- [ ] White-label client portal theming
