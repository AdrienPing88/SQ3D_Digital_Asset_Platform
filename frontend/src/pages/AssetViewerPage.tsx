import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Download, MapPin, MessageSquare } from 'lucide-react';
import { useAsset } from '../hooks/useAssets';
import { formatBytes, assetTypeLabel, statusBadgeClass } from '../utils/format';
import PointCloudViewer from '../components/viewer/PointCloudViewer';

export default function AssetViewerPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const { data: asset, isLoading } = useAsset(assetId!);

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">Loading asset...</div>;
  }
  if (!asset) {
    return <div className="py-20 text-center text-gray-500">Asset not found</div>;
  }

  const isPointCloud = ['las', 'laz', 'e57'].includes(asset.asset_type);
  const isReady = asset.status === 'ready';

  return (
    <div>
      {/* Header */}
      <div className="mb-4">
        <Link
          to={`/projects/${asset.project_id}`}
          className="mb-2 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to project
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">{asset.name}</h1>
            <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
              <span>{assetTypeLabel(asset.asset_type)}</span>
              <span>{formatBytes(asset.file_size_bytes)}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeClass(asset.status)}`}
              >
                {asset.status}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <MapPin className="h-4 w-4" />
              Annotate
            </button>
            <button className="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <Download className="h-4 w-4" />
              Download
            </button>
          </div>
        </div>
      </div>

      {/* Viewer area */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-gray-900">
        {!isReady ? (
          <div className="flex h-[600px] items-center justify-center text-gray-400">
            {asset.status === 'processing' ? (
              <div className="text-center">
                <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-gray-600 border-t-brand-400" />
                <p>Processing asset...</p>
                <p className="mt-1 text-xs text-gray-500">
                  This may take a few minutes for large files
                </p>
              </div>
            ) : asset.status === 'error' ? (
              <div className="text-center text-red-400">
                <p>Processing failed</p>
                <p className="mt-1 text-xs">Check the processing logs for details</p>
              </div>
            ) : (
              <p>Asset is pending processing</p>
            )}
          </div>
        ) : isPointCloud ? (
          <PointCloudViewer assetId={asset.id} tileRootUrl={asset.tile_root_url} />
        ) : (
          <div className="flex h-[600px] items-center justify-center text-gray-400">
            <div className="text-center">
              <p className="text-lg font-medium">Viewer</p>
              <p className="mt-1 text-sm">
                {assetTypeLabel(asset.asset_type)} viewer ready
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Metadata panel */}
      {isReady && Object.keys(asset.spatial_metadata).length > 0 && (
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold text-gray-700">Spatial Metadata</h3>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            {Object.entries(asset.spatial_metadata).map(([key, value]) => (
              <div key={key}>
                <dt className="text-xs text-gray-400">{key}</dt>
                <dd className="font-medium text-gray-700">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Annotations panel */}
      <div className="mt-4 rounded-xl border border-gray-200 bg-white p-5">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-700">
            Annotations ({asset.annotation_count})
          </h3>
        </div>
        {asset.annotation_count === 0 && (
          <p className="mt-3 text-sm text-gray-400">
            No annotations yet. Click "Annotate" to add spatial notes.
          </p>
        )}
      </div>
    </div>
  );
}
