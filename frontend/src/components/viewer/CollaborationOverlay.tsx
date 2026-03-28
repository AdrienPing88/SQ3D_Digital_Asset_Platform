/**
 * CollaborationOverlay — shows connected collaborators and their cursors
 * on top of the viewer canvas.
 */

import { clsx } from 'clsx';
import type { Collaborator } from '../../hooks/usePresence';

// ─────────────────────────────────────────
// Types
// ─────────────────────────────────────────

interface CollaborationOverlayProps {
  collaborators: Collaborator[];
  connected: boolean;
  /** Viewer container dimensions for mapping 3-D positions to 2-D screen. */
  viewportWidth?: number;
  viewportHeight?: number;
}

// ─────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

// ─────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────

function AvatarBadge({ collaborator }: { collaborator: Collaborator }) {
  return (
    <div
      className="group relative flex items-center"
      title={collaborator.display_name}
    >
      <div
        className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white text-xs font-semibold text-white shadow-sm"
        style={{ backgroundColor: collaborator.color }}
      >
        {initials(collaborator.display_name || '??')}
      </div>

      {/* Tooltip */}
      <span className="pointer-events-none absolute -bottom-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-xs text-white opacity-0 shadow transition-opacity group-hover:opacity-100">
        {collaborator.display_name}
      </span>
    </div>
  );
}

function PeerCursor({ collaborator }: { collaborator: Collaborator }) {
  const pos = collaborator.cursor_position;
  if (!pos) return null;

  // Simple screen-space mapping. A real implementation would project
  // the 3-D position through the viewer camera.  For now we use the
  // x/y values directly as percentages (0-100).
  const left = `${Math.min(Math.max(pos.x, 0), 100)}%`;
  const top = `${Math.min(Math.max(pos.y, 0), 100)}%`;

  return (
    <div
      className="pointer-events-none absolute z-30 transition-all duration-100 ease-linear"
      style={{ left, top }}
    >
      {/* Cursor dot */}
      <div
        className="h-3 w-3 rounded-full border border-white shadow-md"
        style={{ backgroundColor: collaborator.color }}
      />
      {/* Name label */}
      <span
        className="ml-3 -mt-1 inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium text-white shadow"
        style={{ backgroundColor: collaborator.color }}
      >
        {collaborator.display_name}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────
// Main component
// ─────────────────────────────────────────

export default function CollaborationOverlay({
  collaborators,
  connected,
}: CollaborationOverlayProps) {
  if (!connected && collaborators.length === 0) return null;

  return (
    <>
      {/* ── Presence bar ─────────────────── */}
      <div className="absolute right-3 top-3 z-40 flex items-center gap-2">
        {/* Connection indicator */}
        <div className="flex items-center gap-1.5 rounded-full bg-gray-900/70 px-3 py-1.5 text-xs text-gray-300 backdrop-blur">
          <span
            className={clsx(
              'inline-block h-2 w-2 rounded-full',
              connected ? 'bg-emerald-400' : 'bg-red-400',
            )}
          />
          {connected ? 'Live' : 'Reconnecting...'}
        </div>

        {/* Collaborator avatars (stacked) */}
        {collaborators.length > 0 && (
          <div className="flex -space-x-2">
            {collaborators.slice(0, 5).map((c) => (
              <AvatarBadge key={c.user_id} collaborator={c} />
            ))}
            {collaborators.length > 5 && (
              <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-gray-700 text-xs font-semibold text-white">
                +{collaborators.length - 5}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Peer cursors on the canvas ──── */}
      {collaborators.map((c) => (
        <PeerCursor key={c.user_id} collaborator={c} />
      ))}
    </>
  );
}
