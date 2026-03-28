export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

export function assetTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    las: 'Point Cloud (LAS)',
    laz: 'Point Cloud (LAZ)',
    e57: 'Point Cloud (E57)',
    orthomosaic: 'Orthomosaic',
    flight_log: 'Flight Log',
    raw_imagery: 'Raw Imagery',
    panorama_360: '360 Panorama',
    panorama_video: '360 Video',
    pdf: 'PDF',
    dwg: 'DWG Drawing',
    dxf: 'DXF Drawing',
    rvt: 'Revit Model',
    obj: '3D Model (OBJ)',
    fbx: '3D Model (FBX)',
    ifc: 'IFC Model',
    glb: '3D Model (GLB)',
    gltf: '3D Model (glTF)',
    geotiff: 'GeoTIFF',
    geojson: 'GeoJSON',
    kml: 'KML',
    shp: 'Shapefile',
    other: 'Other',
  };
  return labels[type] || type;
}

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  ready: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
  archived: 'bg-gray-100 text-gray-600',
};

export function statusBadgeClass(status: string): string {
  return statusColors[status] || 'bg-gray-100 text-gray-600';
}
