import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import * as assetsApi from '../api/assets';

export function useAssets(projectId: string, params?: { asset_type?: string; status?: string }) {
  return useQuery({
    queryKey: ['assets', projectId, params],
    queryFn: () => assetsApi.listAssets(projectId, params),
    enabled: !!projectId,
  });
}

export function useAsset(assetId: string) {
  return useQuery({
    queryKey: ['asset', assetId],
    queryFn: () => assetsApi.getAsset(assetId),
    enabled: !!assetId,
  });
}

export function useDeleteAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: assetsApi.deleteAsset,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] });
      toast.success('Asset archived');
    },
  });
}
