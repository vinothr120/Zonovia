import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type {
  AssetAssignmentResult,
  AssetAssignRequest,
  AssetMovementResult,
  AssetMoveRequest,
  AssetTransitionRequest,
  AssetTransitionResult,
  AssetUnassignRequest,
  LifecycleState,
  LifecycleTransitionDefinition,
} from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

/** Reference-data hook for lifecycle-state name resolution — mirrors useAssetCategories/
 * useAssetTypes/useVendors. */
export function useLifecycleStates() {
  const query = useQuery({
    queryKey: ["lifecycle-states"],
    queryFn: () => api.get<LifecycleState[]>("/asset-lifecycle/states"),
    staleTime: REFERENCE_STALE_TIME,
  });
  const map = useMemo(() => new Map((query.data ?? []).map((s) => [s.id, s])), [query.data]);
  return { ...query, map };
}

/** Reference-data hook for the transition allow-list — mirrors useLifecycleStates. Grouped by
 * from_state_id so LifecycleActions can compute an asset's valid next states in a useMemo
 * without re-scanning the flat list on every render. */
export function useTransitionDefinitions() {
  const query = useQuery({
    queryKey: ["lifecycle-transitions"],
    queryFn: () => api.get<LifecycleTransitionDefinition[]>("/asset-lifecycle/transitions"),
    staleTime: REFERENCE_STALE_TIME,
  });
  const byFromState = useMemo(() => {
    const map = new Map<string, LifecycleTransitionDefinition[]>();
    for (const t of query.data ?? []) {
      const list = map.get(t.from_state_id) ?? [];
      list.push(t);
      map.set(t.from_state_id, list);
    }
    return map;
  }, [query.data]);
  return { ...query, byFromState };
}

/** Shared by all four Flow write mutations below: every one of them invalidates exactly the
 * asset-detail/list queries (["assets"] prefix-matches both) and this asset's history feed —
 * confirmed against AssetDetailPage's and HistoryFeed's actual query keys. Toast wording and
 * inline-error placement stay with the calling component via mutate(body, {onSuccess, onError}). */
function useAssetActionInvalidation(assetId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["assets"] });
    void queryClient.invalidateQueries({ queryKey: ["asset-history", assetId] });
  };
}

export function useTransitionAsset(assetId: string) {
  const invalidate = useAssetActionInvalidation(assetId);
  return useMutation({
    mutationFn: (body: AssetTransitionRequest) => api.post<AssetTransitionResult>(`/assets/${assetId}/transition`, body),
    onSuccess: invalidate,
  });
}

export function useAssignCustodian(assetId: string) {
  const invalidate = useAssetActionInvalidation(assetId);
  return useMutation({
    mutationFn: (body: AssetAssignRequest) => api.post<AssetAssignmentResult>(`/assets/${assetId}/assign`, body),
    onSuccess: invalidate,
  });
}

export function useUnassignCustodian(assetId: string) {
  const invalidate = useAssetActionInvalidation(assetId);
  return useMutation({
    mutationFn: (body: AssetUnassignRequest) => api.post<AssetAssignmentResult>(`/assets/${assetId}/unassign`, body),
    onSuccess: invalidate,
  });
}

export function useMoveAsset(assetId: string) {
  const invalidate = useAssetActionInvalidation(assetId);
  return useMutation({
    mutationFn: (body: AssetMoveRequest) => api.post<AssetMovementResult>(`/assets/${assetId}/move`, body),
    onSuccess: invalidate,
  });
}
