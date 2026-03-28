import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { CameraPose } from '../../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  assetId: string;
  tileRootUrl?: string;
  /** Callback fired when the camera moves – useful for WebSocket syncing. */
  onCameraChange?: (pose: CameraPose) => void;
}

/**
 * Potree metadata.json top-level shape (simplified).
 * We only parse what we need for the initial load.
 */
interface PotreeMetadata {
  version: string;
  boundingBox: {
    min: [number, number, number];
    max: [number, number, number];
  };
  scale: number;
  spacing: number;
  hierarchy: Array<{ name: string; pointCount: number }>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BACKGROUND_COLOR = 0x1a1a2e;
const POINT_SIZE = 2.0;
const DEFAULT_POINT_COUNT = 50_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a random demo point cloud when no tileRootUrl is provided. */
function buildDemoPointCloud(count: number): THREE.Points {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    const i3 = i * 3;
    // Sphere distribution
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = 10 + Math.random() * 5;

    positions[i3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i3 + 2] = r * Math.cos(phi);

    // Color by height
    const t = (positions[i3 + 2]! + 15) / 30;
    colors[i3] = Math.min(1, t * 2);
    colors[i3 + 1] = Math.min(1, 0.3 + t * 0.7);
    colors[i3 + 2] = Math.max(0, 1 - t * 1.5);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: POINT_SIZE,
    vertexColors: true,
    sizeAttenuation: true,
  });

  return new THREE.Points(geometry, material);
}

/**
 * Attempt to load a Potree-tiled point cloud from the given root URL.
 *
 * Expected layout:
 *   <tileRootUrl>/metadata.json
 *   <tileRootUrl>/octree/r/r.bin  (etc.)
 *
 * If the fetch fails we fall back to a demo cloud – this lets the viewer
 * work in development without a real tile server.
 */
async function loadPotreeOctree(
  tileRootUrl: string,
  signal: AbortSignal,
): Promise<THREE.Points> {
  try {
    const metaRes = await fetch(`${tileRootUrl}/metadata.json`, { signal });
    if (!metaRes.ok) throw new Error(`metadata.json: ${metaRes.status}`);
    const meta: PotreeMetadata = await metaRes.json() as PotreeMetadata;

    // Build bounding box
    const min = new THREE.Vector3(...meta.boundingBox.min);
    const max = new THREE.Vector3(...meta.boundingBox.max);
    const center = new THREE.Vector3().addVectors(min, max).multiplyScalar(0.5);

    // Try loading the root node binary
    const binRes = await fetch(`${tileRootUrl}/octree/r/r.bin`, { signal });
    if (!binRes.ok) throw new Error(`root node binary: ${binRes.status}`);
    const buffer = await binRes.arrayBuffer();

    // Parse simple XYZ + RGB (6 floats per point)
    const floats = new Float32Array(buffer);
    const pointCount = Math.floor(floats.length / 6);

    const positions = new Float32Array(pointCount * 3);
    const colors = new Float32Array(pointCount * 3);
    for (let i = 0; i < pointCount; i++) {
      const src = i * 6;
      const dst = i * 3;
      positions[dst] = floats[src]! - center.x;
      positions[dst + 1] = floats[src + 1]! - center.y;
      positions[dst + 2] = floats[src + 2]! - center.z;
      colors[dst] = floats[src + 3]! / 255;
      colors[dst + 1] = floats[src + 4]! / 255;
      colors[dst + 2] = floats[src + 5]! / 255;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
      size: meta.scale ?? POINT_SIZE,
      vertexColors: true,
      sizeAttenuation: true,
    });

    return new THREE.Points(geometry, material);
  } catch {
    // Fallback: generate demo cloud so the viewer still renders something.
    console.warn(
      '[PointCloudViewer] Could not load Potree octree – using demo point cloud.',
    );
    return buildDemoPointCloud(DEFAULT_POINT_COUNT);
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PointCloudViewer({
  assetId,
  tileRootUrl,
  onCameraChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const frameIdRef = useRef<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Expose camera pose to React state for WebSocket syncing.
  const emitCameraPose = useCallback(
    (camera: THREE.PerspectiveCamera, target: THREE.Vector3) => {
      if (!onCameraChange) return;
      onCameraChange({
        position: [camera.position.x, camera.position.y, camera.position.z],
        target: [target.x, target.y, target.z],
        up: [camera.up.x, camera.up.y, camera.up.z],
      });
    },
    [onCameraChange],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const abortController = new AbortController();

    // --- Scene setup ---
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BACKGROUND_COLOR);

    // Ambient + directional light (mainly for future mesh overlays)
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);

    // Camera
    const width = container.clientWidth;
    const height = container.clientHeight;
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 10_000);
    camera.position.set(0, 0, 30);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.minDistance = 1;
    controls.maxDistance = 500;
    controlsRef.current = controls;

    controls.addEventListener('change', () => {
      emitCameraPose(camera, controls.target);
    });

    // --- Load point cloud ---
    const loadCloud = async () => {
      try {
        const points = tileRootUrl
          ? await loadPotreeOctree(tileRootUrl, abortController.signal)
          : buildDemoPointCloud(DEFAULT_POINT_COUNT);

        if (abortController.signal.aborted) return;

        scene.add(points);

        // Fit camera to bounding sphere
        points.geometry.computeBoundingSphere();
        const sphere = points.geometry.boundingSphere;
        if (sphere) {
          const radius = sphere.radius || 15;
          camera.position.set(
            sphere.center.x,
            sphere.center.y,
            sphere.center.z + radius * 2.5,
          );
          controls.target.copy(sphere.center);
          controls.update();
        }

        setLoading(false);
      } catch (err) {
        if (!abortController.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Failed to load point cloud');
          setLoading(false);
        }
      }
    };

    void loadCloud();

    // --- Render loop ---
    const animate = () => {
      frameIdRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // --- Resize handler ---
    const onResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    // --- Cleanup ---
    return () => {
      abortController.abort();
      window.removeEventListener('resize', onResize);
      cancelAnimationFrame(frameIdRef.current);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }

      // Dispose all scene geometries / materials
      scene.traverse((obj) => {
        if (obj instanceof THREE.Points || obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          const mat = obj.material;
          if (Array.isArray(mat)) {
            mat.forEach((m) => m.dispose());
          } else {
            mat.dispose();
          }
        }
      });

      rendererRef.current = null;
      controlsRef.current = null;
    };
  }, [tileRootUrl, assetId, emitCameraPose]);

  return (
    <div
      ref={containerRef}
      className="relative h-[600px] w-full bg-gray-950"
      data-asset-id={assetId}
    >
      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-950/80">
          <div className="text-center text-gray-400">
            <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-blue-400" />
            <p className="text-sm">Loading point cloud&hellip;</p>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-950/80">
          <div className="text-center text-red-400">
            <p className="text-sm font-medium">Failed to load point cloud</p>
            <p className="mt-1 text-xs text-red-500">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
