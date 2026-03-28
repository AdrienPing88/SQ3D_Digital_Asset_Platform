/**
 * Real-time presence hook — connects to the Socket.IO server,
 * joins a project room, and tracks collaborator cursors / presence.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { useAuthStore } from '../store/authStore';
import type { AnnotationPosition, Annotation } from '../types';

// ─────────────────────────────────────────
// Types
// ─────────────────────────────────────────

export interface Collaborator {
  user_id: string;
  display_name: string;
  cursor_position?: AnnotationPosition;
  /** Assigned colour for this session. */
  color: string;
}

interface CursorMovedPayload {
  user_id: string;
  display_name: string;
  position: { x: number; y: number; z: number };
}

interface UserEventPayload {
  user_id: string;
  display_name: string;
  timestamp: string;
}

interface AnnotationEventPayload {
  user_id: string;
  display_name: string;
  annotation: Annotation;
  timestamp: string;
}

interface JoinResponse {
  status: string;
  project_id: string;
  members: Array<{
    user_id: string;
    display_name: string;
    cursor_position?: AnnotationPosition;
  }>;
}

export interface UsePresenceReturn {
  collaborators: Collaborator[];
  connected: boolean;
  updateCursor: (position: { x: number; y: number; z: number }) => void;
  sendAnnotation: (data: Record<string, unknown>) => void;
  sendAnnotationUpdate: (data: Record<string, unknown>) => void;
}

// ─────────────────────────────────────────
// Colour palette for peer cursors
// ─────────────────────────────────────────

const CURSOR_COLORS = [
  '#EF4444', // red-500
  '#F59E0B', // amber-500
  '#10B981', // emerald-500
  '#3B82F6', // blue-500
  '#8B5CF6', // violet-500
  '#EC4899', // pink-500
  '#14B8A6', // teal-500
  '#F97316', // orange-500
];

function pickColor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = (hash << 5) - hash + userId.charCodeAt(i);
    hash |= 0;
  }
  return CURSOR_COLORS[Math.abs(hash) % CURSOR_COLORS.length] ?? '#3B82F6';
}

// ─────────────────────────────────────────
// Hook
// ─────────────────────────────────────────

export function usePresence(projectId: string | undefined): UsePresenceReturn {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const socketRef = useRef<Socket | null>(null);
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [connected, setConnected] = useState(false);

  // Stable helpers to mutate collaborator list
  const upsertCollaborator = useCallback(
    (userId: string, displayName: string, cursor?: AnnotationPosition) => {
      setCollaborators((prev) => {
        const idx = prev.findIndex((c) => c.user_id === userId);
        const entry: Collaborator = {
          user_id: userId,
          display_name: displayName,
          cursor_position: cursor,
          color: pickColor(userId),
        };
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...next[idx], ...entry };
          return next;
        }
        return [...prev, entry];
      });
    },
    [],
  );

  const removeCollaborator = useCallback((userId: string) => {
    setCollaborators((prev) => prev.filter((c) => c.user_id !== userId));
  }, []);

  // ── Connection lifecycle ──────────────
  useEffect(() => {
    if (!projectId || !token) return;

    const wsBase =
      import.meta.env.VITE_WS_BASE_URL ||
      import.meta.env.VITE_API_BASE_URL ||
      window.location.origin;

    const socket = io(wsBase, {
      path: '/ws/socket.io',
      auth: { token },
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      setConnected(true);

      // Join project room
      socket.emit(
        'join_project',
        {
          project_id: projectId,
          display_name: user?.display_name ?? '',
        },
        (response: JoinResponse) => {
          if (response?.members) {
            const initial = response.members.map((m) => ({
              user_id: m.user_id,
              display_name: m.display_name,
              cursor_position: m.cursor_position,
              color: pickColor(m.user_id),
            }));
            setCollaborators(initial);
          }
        },
      );
    });

    socket.on('disconnect', () => {
      setConnected(false);
    });

    // ── Peer events ───────────────────────
    socket.on('user.joined', (payload: UserEventPayload) => {
      upsertCollaborator(payload.user_id, payload.display_name);
    });

    socket.on('user.left', (payload: UserEventPayload) => {
      removeCollaborator(payload.user_id);
    });

    socket.on('cursor.moved', (payload: CursorMovedPayload) => {
      upsertCollaborator(payload.user_id, payload.display_name, {
        x: payload.position.x,
        y: payload.position.y,
        z: payload.position.z,
      });
    });

    socket.on('annotation.created', (payload: AnnotationEventPayload) => {
      // Components can subscribe to this via a global event bus or query
      // invalidation. For now we just log it so the overlay stays focused.
      console.debug('[ws] annotation.created', payload);
    });

    socket.on('annotation.updated', (payload: AnnotationEventPayload) => {
      console.debug('[ws] annotation.updated', payload);
    });

    // ── Cleanup ───────────────────────────
    return () => {
      socket.emit('leave_project', { project_id: projectId });
      socket.disconnect();
      socketRef.current = null;
      setCollaborators([]);
      setConnected(false);
    };
  }, [projectId, token, user?.display_name, upsertCollaborator, removeCollaborator]);

  // ── Exposed actions ────────────────────

  const updateCursor = useCallback(
    (position: { x: number; y: number; z: number }) => {
      socketRef.current?.emit('cursor_move', position);
    },
    [],
  );

  const sendAnnotation = useCallback(
    (data: Record<string, unknown>) => {
      socketRef.current?.emit('annotation_created', data);
    },
    [],
  );

  const sendAnnotationUpdate = useCallback(
    (data: Record<string, unknown>) => {
      socketRef.current?.emit('annotation_updated', data);
    },
    [],
  );

  return { collaborators, connected, updateCursor, sendAnnotation, sendAnnotationUpdate };
}
