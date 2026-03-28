"""V1 API router — aggregates all endpoint modules."""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, projects, assets, annotations

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(assets.router, tags=["assets"])
api_router.include_router(annotations.router, tags=["annotations"])
