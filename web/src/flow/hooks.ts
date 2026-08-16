import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type { LifecycleState } from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

/** Reference-data hook for lifecycle-state name resolution — mirrors useAssetCategories/
 * useAssetTypes/useVendors. No mutation hooks here: Flow write actions (transition/assign/
 * move) are explicitly out of scope this increment. */
export function useLifecycleStates() {
  const query = useQuery({
    queryKey: ["lifecycle-states"],
    queryFn: () => api.get<LifecycleState[]>("/asset-lifecycle/states"),
    staleTime: REFERENCE_STALE_TIME,
  });
  const map = useMemo(() => new Map((query.data ?? []).map((s) => [s.id, s])), [query.data]);
  return { ...query, map };
}
