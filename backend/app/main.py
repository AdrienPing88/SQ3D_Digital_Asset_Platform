"""
SQ3D Digital Asset Platform — FastAPI Backend
Entry point: uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import engine
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise connection pools, Redis client, etc.
    yield
    # Shutdown: close connections cleanly
    await engine.dispose()


app = FastAPI(
    title="SQ3D Digital Asset Platform API",
    description="Collaborative DAM platform for geospatial and construction data.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ──────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ──────────────────────────────────────────
# Routers
# ──────────────────────────────────────────
app.include_router(api_router, prefix="/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
