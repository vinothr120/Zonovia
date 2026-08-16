import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../core/apiClient";
import type { AssetLocation } from "./types";

const REFERENCE_STALE_TIME = 5 * 60 * 1000;

/** There's no flat "list all locations" endpoint — only root-level GET /asset-locations and
 * per-node GET /asset-locations/{id}/descendants. This fetches roots, then one /descendants
 * call per root (O(root count), not O(location count)), and concatenates into one flat cached
 * array that serves both the id -> name lookup map and the tree browser itself. */
export function useAssetLocations() {
  const query = useQuery({
    queryKey: ["asset-locations"],
    queryFn: async () => {
      const roots = await api.get<AssetLocation[]>("/asset-locations");
      const descendantLists = await Promise.all(
        roots.map((root) => api.get<AssetLocation[]>(`/asset-locations/${root.id}/descendants`)),
      );
      return [...roots, ...descendantLists.flat()];
    },
    staleTime: REFERENCE_STALE_TIME,
  });
  const map = useMemo(() => new Map((query.data ?? []).map((loc) => [loc.id, loc])), [query.data]);
  return { ...query, map };
}

/** Walks parent_location_id in memory from the already-cached flat list — the dedicated
 * /ancestors endpoint would be a redundant round trip once the full tree is resident. Returns
 * root-first segment names, e.g. ["Building A", "Floor 2", "Room 201"]. */
export function locationBreadcrumb(locationId: string | null | undefined, map: Map<string, AssetLocation>): string[] {
  const chain: string[] = [];
  const seen = new Set<string>();
  let current = locationId ? map.get(locationId) : undefined;
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    chain.unshift(current.name);
    current = current.parent_location_id ? map.get(current.parent_location_id) : undefined;
  }
  return chain;
}

/** Flattens the tree into select-friendly options, root-first, indented by depth via a DFS
 * pre-order walk (siblings ordered by sort_order then name) — used by the location picker in
 * the create/edit form. */
export function indentedLocationOptions(locations: AssetLocation[]): { id: string; label: string }[] {
  const byParent = new Map<string | null, AssetLocation[]>();
  for (const loc of locations) {
    const key = loc.parent_location_id;
    const siblings = byParent.get(key) ?? [];
    siblings.push(loc);
    byParent.set(key, siblings);
  }
  for (const siblings of byParent.values()) {
    siblings.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
  }

  const options: { id: string; label: string }[] = [];
  function walk(parentId: string | null, depth: number) {
    for (const loc of byParent.get(parentId) ?? []) {
      options.push({ id: loc.id, label: `${"— ".repeat(depth)}${loc.name}` });
      walk(loc.id, depth + 1);
    }
  }
  walk(null, 0);
  return options;
}
