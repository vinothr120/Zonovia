import { useMemo } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type { Asset } from "../assets/types";
import type {
  CycleReport,
  InventoryCount,
  InventoryCycle,
  InventoryCycleCreateInput,
  InventoryVerificationInput,
  ReconciliationAction,
  ReconciliationInput,
} from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

/** GET /inventory/cycles has no pagination wired through the router — fixed at the service's
 * default limit=20, a real backend limitation surfaced by CyclesListPage rather than papered
 * over here. */
export function useInventoryCycles() {
  return useQuery({
    queryKey: ["inventory-cycles"],
    queryFn: () => api.get<InventoryCycle[]>("/inventory/cycles"),
  });
}

export function useInventoryCycle(cycleId: string | undefined) {
  return useQuery({
    queryKey: ["inventory-cycles", cycleId],
    queryFn: () => api.get<InventoryCycle>(`/inventory/cycles/${cycleId}`),
    enabled: !!cycleId,
  });
}

/** Shared by create/start/complete/cancel — every one of them changes the cycle's row, which
 * both the list and the detail query key are prefixed by, so a single invalidateQueries call
 * (react-query prefix-matches ["inventory-cycles", id] under ["inventory-cycles"]) covers both,
 * same convention as flow/hooks.ts's useAssetActionInvalidation. */
function useCycleListInvalidation() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["inventory-cycles"] });
}

export function useCreateCycle() {
  const invalidate = useCycleListInvalidation();
  return useMutation({
    mutationFn: (body: InventoryCycleCreateInput) => api.post<InventoryCycle>("/inventory/cycles", body),
    onSuccess: invalidate,
  });
}

export function useStartCycle(cycleId: string) {
  const invalidate = useCycleListInvalidation();
  return useMutation({
    mutationFn: () => api.post<InventoryCycle>(`/inventory/cycles/${cycleId}/start`),
    onSuccess: invalidate,
  });
}

export function useCompleteCycle(cycleId: string) {
  const invalidate = useCycleListInvalidation();
  return useMutation({
    mutationFn: () => api.post<InventoryCycle>(`/inventory/cycles/${cycleId}/complete`),
    onSuccess: invalidate,
  });
}

export function useCancelCycle(cycleId: string) {
  const invalidate = useCycleListInvalidation();
  return useMutation({
    mutationFn: () => api.post<InventoryCycle>(`/inventory/cycles/${cycleId}/cancel`),
    onSuccess: invalidate,
  });
}

export function useCycleCounts(cycleId: string | undefined) {
  return useQuery({
    queryKey: ["inventory-counts", cycleId],
    queryFn: () => api.get<InventoryCount[]>(`/inventory/cycles/${cycleId}/counts`),
    enabled: !!cycleId,
  });
}

// Enabled purely off cycleId, not cycle status — list_expected_assets (and therefore the
// report) works against a draft cycle too, so CycleDetailPage can show a live all-expected/
// zero-verified preview before the cycle is ever started.
export function useCycleReport(cycleId: string | undefined) {
  return useQuery({
    queryKey: ["inventory-report", cycleId],
    queryFn: () => api.get<CycleReport>(`/inventory/cycles/${cycleId}/report`),
    enabled: !!cycleId,
  });
}

/** Invalidates counts + report together — every verification changes both the feed and the
 * report's verified/missing/discrepancy breakdown. */
export function useRecordVerification(cycleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: InventoryVerificationInput) => api.post<InventoryCount>(`/inventory/cycles/${cycleId}/counts`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory-counts", cycleId] });
      void queryClient.invalidateQueries({ queryKey: ["inventory-report", cycleId] });
    },
  });
}

export function useReconciliations(cycleId: string | undefined) {
  return useQuery({
    queryKey: ["inventory-reconciliations", cycleId],
    queryFn: () => api.get<ReconciliationAction[]>(`/inventory/cycles/${cycleId}/reconciliations`),
    enabled: !!cycleId,
  });
}

export function useRecordReconciliation(cycleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ReconciliationInput) => api.post<ReconciliationAction>(`/inventory/cycles/${cycleId}/reconciliations`, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["inventory-reconciliations", cycleId] }),
  });
}

/** Asset-name resolution for cycle-scoped views. Dedupes input and fetches each id via
 * useQueries over the SAME ["assets", id] query key AssetDetailPage already uses — cache is
 * shared across pages — rather than a new batch endpoint (none exists), since a cycle's scope
 * is a real physical location subtree, realistically tens of assets, not an unbounded set
 * worth building batch-fetch infrastructure for. Per-id failures are silently excluded from
 * the result map — same "unknown, not a failure" posture as users/hooks.ts's custodianLabel —
 * a row that can't resolve a name shows the raw id instead of breaking the page. */
export function useAssetsLookup(ids: string[]) {
  const uniqueIds = useMemo(() => [...new Set(ids)], [ids]);
  const results = useQueries({
    queries: uniqueIds.map((id) => ({
      queryKey: ["assets", id],
      queryFn: () => api.get<Asset>(`/assets/${id}`),
      staleTime: REFERENCE_STALE_TIME,
    })),
  });
  const map = useMemo(() => {
    const m = new Map<string, Asset>();
    for (const r of results) {
      if (r.data) m.set(r.data.id, r.data);
    }
    return m;
  }, [results]);
  return { map };
}

/** Resolved name if present in the lookup map; otherwise (still loading, or the per-id fetch
 * failed) a neutral fallback with a truncated id — same convention as custodianLabel. */
export function assetLabel(assetId: string, map: Map<string, Asset>): string {
  return map.get(assetId)?.name ?? `Asset (${assetId.slice(0, 8)}…)`;
}
