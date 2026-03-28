import { useEffect, useRef } from 'react';

interface Props {
  assetId: string;
  tileRootUrl?: string;
}

export default function PointCloudViewer({ assetId, tileRootUrl }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!tileRootUrl || !containerRef.current) return;

    // Potree.js integration point.
    // In production, this would load Potree from CDN and initialize:
    //
    //   const viewer = new Potree.Viewer(containerRef.current);
    //   Potree.loadPointCloud(tileRootUrl, 'cloud', (e) => {
    //     viewer.scene.addPointCloud(e.pointcloud);
    //     viewer.fitToScreen();
    //   });
    //
    // For now, we show a placeholder with the streaming URL.

    return () => {
      // Cleanup viewer on unmount
    };
  }, [tileRootUrl, assetId]);

  return (
    <div
      ref={containerRef}
      className="relative flex h-[600px] items-center justify-center bg-gradient-to-b from-gray-900 to-gray-950"
    >
      <div className="text-center text-gray-400">
        <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-gray-800 p-4">
          <svg viewBox="0 0 24 24" fill="none" className="h-full w-full">
            <circle cx="4" cy="4" r="1.5" fill="currentColor" opacity="0.5" />
            <circle cx="12" cy="3" r="1.5" fill="currentColor" opacity="0.7" />
            <circle cx="20" cy="5" r="1.5" fill="currentColor" opacity="0.4" />
            <circle cx="7" cy="10" r="1.5" fill="currentColor" opacity="0.8" />
            <circle cx="15" cy="9" r="1.5" fill="currentColor" opacity="0.6" />
            <circle cx="3" cy="16" r="1.5" fill="currentColor" opacity="0.3" />
            <circle cx="11" cy="15" r="1.5" fill="currentColor" opacity="0.9" />
            <circle cx="19" cy="14" r="1.5" fill="currentColor" opacity="0.5" />
            <circle cx="8" cy="20" r="1.5" fill="currentColor" opacity="0.6" />
            <circle cx="16" cy="20" r="1.5" fill="currentColor" opacity="0.4" />
          </svg>
        </div>
        <p className="text-lg font-medium">Point Cloud Viewer</p>
        <p className="mt-1 text-sm text-gray-500">
          Potree.js viewer will render here when configured
        </p>
        {tileRootUrl && (
          <p className="mt-2 text-xs text-gray-600">
            Tile stream: ready
          </p>
        )}
      </div>
    </div>
  );
}
