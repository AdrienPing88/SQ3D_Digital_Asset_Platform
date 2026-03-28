"""
Real-time collaboration WebSocket server using python-socketio.

Provides per-project rooms with presence tracking, cursor broadcasting,
and live annotation events.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import socketio
from jose import JWTError

from app.core.config import settings
from app.core.security import decode_token

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# Socket.IO server
# ──────────────────────────────────────────

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.ALLOWED_ORIGINS,
    logger=False,
    engineio_logger=False,
)

# In-memory presence store: sid -> user metadata
_sessions: dict[str, dict[str, Any]] = {}

# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────


def _room_name(project_id: str) -> str:
    """Canonical room name for a project."""
    return f"project:{project_id}"


async def _authenticate(environ: dict) -> dict | None:
    """Extract and validate JWT from the connection handshake.

    The client should pass the token either as a query param ``?token=<jwt>``
    or in the ``auth`` dict (Socket.IO v4+).
    """
    # Try auth dict first (preferred)
    auth: dict | None = environ.get("auth") or environ.get("HTTP_AUTHORIZATION")
    token: str | None = None

    if isinstance(auth, dict):
        token = auth.get("token")
    elif isinstance(auth, str) and auth.startswith("Bearer "):
        token = auth[7:]

    # Fallback: query string
    if not token:
        query_string = environ.get("QUERY_STRING", "")
        for part in query_string.split("&"):
            if part.startswith("token="):
                token = part[6:]
                break

    if not token:
        return None

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        return {
            "user_id": payload["sub"],
            "org_id": payload.get("org_id", ""),
            "role": payload.get("role", "member"),
        }
    except JWTError:
        logger.warning("WebSocket auth failed: invalid token")
        return None


# ──────────────────────────────────────────
# Event handlers
# ──────────────────────────────────────────


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> bool:
    """Authenticate user and optionally join a project room."""
    # Merge auth from different sources
    if auth:
        environ["auth"] = auth

    user = await _authenticate(environ)
    if user is None:
        logger.info("Rejecting unauthenticated WebSocket connection")
        return False

    _sessions[sid] = {
        **user,
        "sid": sid,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "project_id": None,
        "display_name": user.get("display_name", ""),
        "cursor_position": None,
    }

    logger.info("WebSocket connected: sid=%s user=%s", sid, user["user_id"])
    return True


@sio.event
async def disconnect(sid: str) -> None:
    """Remove user from session tracking and notify room peers."""
    session = _sessions.pop(sid, None)
    if not session:
        return

    project_id = session.get("project_id")
    if project_id:
        room = _room_name(project_id)
        await sio.emit(
            "user.left",
            {
                "user_id": session["user_id"],
                "display_name": session.get("display_name", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            room=room,
            skip_sid=sid,
        )

    logger.info("WebSocket disconnected: sid=%s user=%s", sid, session.get("user_id"))


@sio.event
async def join_project(sid: str, data: dict) -> dict[str, Any]:
    """Join a project room and notify peers.

    Expects: ``{ "project_id": "<uuid>", "display_name": "<name>" }``
    """
    session = _sessions.get(sid)
    if not session:
        return {"error": "not_authenticated"}

    project_id = data.get("project_id")
    if not project_id:
        return {"error": "project_id_required"}

    display_name = data.get("display_name", "")

    # Leave any previous room
    old_project = session.get("project_id")
    if old_project:
        old_room = _room_name(old_project)
        sio.leave_room(sid, old_room)
        await sio.emit(
            "user.left",
            {
                "user_id": session["user_id"],
                "display_name": session.get("display_name", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            room=old_room,
            skip_sid=sid,
        )

    # Join new room
    room = _room_name(project_id)
    sio.enter_room(sid, room)
    session["project_id"] = project_id
    session["display_name"] = display_name

    # Notify room peers
    await sio.emit(
        "user.joined",
        {
            "user_id": session["user_id"],
            "display_name": display_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        room=room,
        skip_sid=sid,
    )

    # Return current room members
    members = [
        {
            "user_id": s["user_id"],
            "display_name": s.get("display_name", ""),
            "cursor_position": s.get("cursor_position"),
        }
        for s in _sessions.values()
        if s.get("project_id") == project_id and s["sid"] != sid
    ]

    logger.info(
        "User %s joined project %s (room has %d other members)",
        session["user_id"],
        project_id,
        len(members),
    )

    return {"status": "joined", "project_id": project_id, "members": members}


@sio.event
async def leave_project(sid: str, data: dict | None = None) -> dict[str, str]:
    """Leave the current project room."""
    session = _sessions.get(sid)
    if not session:
        return {"error": "not_authenticated"}

    project_id = session.get("project_id")
    if not project_id:
        return {"status": "not_in_room"}

    room = _room_name(project_id)
    sio.leave_room(sid, room)

    await sio.emit(
        "user.left",
        {
            "user_id": session["user_id"],
            "display_name": session.get("display_name", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        room=room,
        skip_sid=sid,
    )

    session["project_id"] = None
    session["cursor_position"] = None

    return {"status": "left", "project_id": project_id}


# ──────────────────────────────────────────
# Cursor tracking
# ──────────────────────────────────────────


@sio.event
async def cursor_move(sid: str, data: dict) -> None:
    """Broadcast cursor position to room peers.

    Expects: ``{ "x": float, "y": float, "z": float }``
    """
    session = _sessions.get(sid)
    if not session:
        return

    project_id = session.get("project_id")
    if not project_id:
        return

    position = {
        "x": data.get("x", 0),
        "y": data.get("y", 0),
        "z": data.get("z", 0),
    }

    session["cursor_position"] = position

    await sio.emit(
        "cursor.moved",
        {
            "user_id": session["user_id"],
            "display_name": session.get("display_name", ""),
            "position": position,
        },
        room=_room_name(project_id),
        skip_sid=sid,
    )


# ──────────────────────────────────────────
# Annotation events
# ──────────────────────────────────────────


@sio.event
async def annotation_created(sid: str, data: dict) -> None:
    """Broadcast a newly created annotation to room peers.

    Expects the full annotation payload from the REST API response.
    """
    session = _sessions.get(sid)
    if not session:
        return

    project_id = session.get("project_id")
    if not project_id:
        return

    await sio.emit(
        "annotation.created",
        {
            "user_id": session["user_id"],
            "display_name": session.get("display_name", ""),
            "annotation": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        room=_room_name(project_id),
        skip_sid=sid,
    )

    logger.debug(
        "Annotation created by %s in project %s",
        session["user_id"],
        project_id,
    )


@sio.event
async def annotation_updated(sid: str, data: dict) -> None:
    """Broadcast an annotation edit to room peers.

    Expects the updated annotation payload.
    """
    session = _sessions.get(sid)
    if not session:
        return

    project_id = session.get("project_id")
    if not project_id:
        return

    await sio.emit(
        "annotation.updated",
        {
            "user_id": session["user_id"],
            "display_name": session.get("display_name", ""),
            "annotation": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        room=_room_name(project_id),
        skip_sid=sid,
    )

    logger.debug(
        "Annotation updated by %s in project %s",
        session["user_id"],
        project_id,
    )


# ──────────────────────────────────────────
# ASGI app for mounting
# ──────────────────────────────────────────

socketio_app = socketio.ASGIApp(sio, socketio_path="/socket.io")
