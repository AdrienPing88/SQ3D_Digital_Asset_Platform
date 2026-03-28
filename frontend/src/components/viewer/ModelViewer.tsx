import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { CameraPose } from '../../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  assetId: string;
  /** URL to a GLB / GLTF file. */
  modelUrl?: string;
  /** Callback fired when the camera moves. */
  onCameraChange?: (pose: CameraPose) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BACKGROUND_COLOR = 0x1a1a2e;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a simple placeholder box when no model URL is provided. */
function buildPlaceholderScene(): THREE.Group {
  const group = new THREE.Group();

  const geometry = new THREE.BoxGeometry(4, 4, 4);
  const material = new THREE.MeshStandardMaterial({
    color: 0x4488cc,
    metalness: 0.3,
    roughness: 0.7,
    wireframe: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  group.add(mesh);

  // Add a wireframe overlay
  const wireGeo = new THREE.EdgesGeometry(geometry);
  const wireMat = new THREE.LineBasicMaterial({ color: 0x88bbff, transparent: true, opacity: 0.4 });
  group.add(new THREE.LineSegments(wireGeo, wireMat));

  // Ground grid
  const grid = new THREE.GridHelper(20, 20, 0x444466, 0x333355);
  grid.position.y = -2;
  group.add(grid);

  return group;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ModelViewer({
  assetId,
  modelUrl,
  onCameraChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const frameIdRef = useRef<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

    // --- Scene ---
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BACKGROUND_COLOR);

    // Lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
    dirLight.position.set(5, 10, 7);
    dirLight.castShadow = true;
    scene.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0xaabbff, 0.4);
    fillLight.position.set(-5, 3, -5);
    scene.add(fillLight);

    // Camera
    const width = container.clientWidth;
    const height = container.clientHeight;
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 5_000);
    camera.position.set(8, 6, 8);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.minDistance = 0.5;
    controls.maxDistance = 500;

    controls.addEventListener('change', () => {
      emitCameraPose(camera, controls.target);
    });

    // --- Load model ---
    const loadModel = async () => {
      try {
        if (!modelUrl) {
          scene.add(buildPlaceholderScene());
          setLoading(false);
          return;
        }

        const loader = new GLTFLoader();
        const gltf = await loader.loadAsync(modelUrl);

        scene.add(gltf.scene);

        // Fit camera to loaded model
        const box = new THREE.Box3().setFromObject(gltf.scene);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const distance = maxDim * 2;

        camera.position.set(
          center.x + distance * 0.7,
          center.y + distance * 0.5,
          center.z + distance * 0.7,
        );
        controls.target.copy(center);
        controls.update();

        setLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load 3D model');
        setLoading(false);
      }
    };

    void loadModel();

    // --- Render loop ---
    const animate = () => {
      frameIdRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // --- Resize ---
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
      window.removeEventListener('resize', onResize);
      cancelAnimationFrame(frameIdRef.current);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }

      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          const mat = obj.material;
          if (Array.isArray(mat)) {
            mat.forEach((m) => m.dispose());
          } else {
            (mat as THREE.Material).dispose();
          }
        }
      });

      rendererRef.current = null;
    };
  }, [modelUrl, assetId, emitCameraPose]);

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
            <p className="text-sm">Loading 3D model&hellip;</p>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-950/80">
          <div className="text-center text-red-400">
            <p className="text-sm font-medium">Failed to load model</p>
            <p className="mt-1 text-xs text-red-500">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
