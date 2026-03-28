"""
Dev seed data for SQ3D Digital Asset Platform.
Run from the project root with venv active:
    python -m database.seeds.dev_seed
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env"))

import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.security import hash_password

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with SessionLocal() as db:
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        member_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Organization
        await db.execute(text("""
            INSERT INTO organizations (id, name, plan, storage_quota_bytes, storage_used_bytes, settings)
            VALUES (:id, :name, :plan, :quota, :used, CAST(:settings AS jsonb))
            ON CONFLICT DO NOTHING
        """), {"id": str(org_id), "name": "SQ3D Demo Org", "plan": "pro",
               "quota": 107374182400, "used": 0, "settings": "{}"})

        # Admin user
        await db.execute(text("""
            INSERT INTO users (id, org_id, email, display_name, hashed_password, global_role)
            VALUES (:id, :org_id, :email, :name, :pw, :role)
            ON CONFLICT (email) DO NOTHING
        """), {"id": str(admin_id), "org_id": str(org_id), "email": "admin@sq3d.io",
               "name": "Admin User", "pw": hash_password("password123"), "role": "org_admin"})

        # Member user
        await db.execute(text("""
            INSERT INTO users (id, org_id, email, display_name, hashed_password, global_role)
            VALUES (:id, :org_id, :email, :name, :pw, :role)
            ON CONFLICT (email) DO NOTHING
        """), {"id": str(member_id), "org_id": str(org_id), "email": "member@sq3d.io",
               "name": "Member User", "pw": hash_password("password123"), "role": "member"})

        # Project
        await db.execute(text("""
            INSERT INTO projects (id, org_id, created_by, name, description, coordinate_system, metadata)
            VALUES (:id, :org_id, :created_by, :name, :desc, :cs, CAST(:meta AS jsonb))
            ON CONFLICT DO NOTHING
        """), {"id": str(project_id), "org_id": str(org_id), "created_by": str(admin_id),
               "name": "Demo Site Survey", "desc": "Sample point cloud and drone imagery project",
               "cs": "EPSG:4326", "meta": "{}"})

        # Project permissions
        for user_id, role in [(admin_id, "owner"), (member_id, "viewer")]:
            await db.execute(text("""
                INSERT INTO project_permissions (id, project_id, user_id, role, granted_by)
                VALUES (:id, :project_id, :user_id, :role, :granted_by)
                ON CONFLICT (project_id, user_id) DO NOTHING
            """), {"id": str(uuid.uuid4()), "project_id": str(project_id),
                   "user_id": str(user_id), "role": role, "granted_by": str(admin_id)})

        await db.commit()
        print("Seed complete")
        print(f"  Org:     SQ3D Demo Org  ({org_id})")
        print(f"  Admin:   admin@sq3d.io / password123")
        print(f"  Member:  member@sq3d.io / password123")
        print(f"  Project: Demo Site Survey  ({project_id})")


asyncio.run(seed())
