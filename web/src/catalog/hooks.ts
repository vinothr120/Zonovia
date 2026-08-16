import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type { AssetCategory, AssetType, Vendor } from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

/** Small reference-data sets fetched once and cached for 5 minutes, exposing both the raw list
 * (for catalog pages/selects) and an id -> record lookup Map (for FK-to-name resolution on
 * every other page) — never N+1 per-row fetches. `page_size: 100` is a generous cap; catalog
 * tenants are expected to have at most a few dozen categories/types/vendors. */
export function useAssetCategories() {
  const query = useQuery({
    queryKey: ["asset-categories"],
    queryFn: () => api.get<AssetCategory[]>("/asset-categories", { page_size: 100 }),
    staleTime: REFERENCE_STALE_TIME,
  });
  const map = useMemo(() => new Map((query.data ?? []).map((c) => [c.id, c])), [query.data]);
  return { ...query, map };
}

export function useAssetTypes() {
  const query = useQuery({
    queryKey: ["asset-types"],
    queryFn: () => api.get<AssetType[]>("/asset-types", { page_size: 100 }),
    staleTime: REFERENCE_STALE_TIME,
  });
  const map = useMemo(() => new Map((query.data ?? []).map((t) => [t.id, t])), [query.data]);
  return { ...query, map };
}

export function useVendors() {
  const query = useQuery({
    queryKey: ["vendors"],
    queryFn: () => api.get<Vendor[]>("/vendors", { page_size: 100 }),
    staleTime: REFERENCE_STALE_TIME,
  });
  const map = useMemo(() => new Map((query.data ?? []).map((v) => [v.id, v])), [query.data]);
  return { ...query, map };
}
