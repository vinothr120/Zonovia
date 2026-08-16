import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { api, apiRequestWithMeta } from "../core/apiClient";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { Pagination } from "../core/ui/Pagination";
import { useAssetTypes } from "../catalog/hooks";
import { useAssetLocations } from "../locations/hooks";
import { useLifecycleStates } from "../flow/hooks";
import type { Asset } from "./types";

const PAGE_SIZE = 20;
const FILTERED_PAGE_SIZE = 100;

export function AssetListPage() {
  const { me } = useAuth();
  const canCreate = me?.permissions.includes("assets.create") ?? false;

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [typeId, setTypeId] = useState("");
  const [locationId, setLocationId] = useState("");

  const typesQuery = useAssetTypes();
  const locationsQuery = useAssetLocations();
  const statesQuery = useLifecycleStates();

  const isFiltered = search.trim() !== "" || typeId !== "" || locationId !== "";

  // Unfiltered: real server-side pagination — an asset registry can plausibly reach thousands
  // of rows. Filtered: GET /assets has no search/filter param at all, so the moment a filter is
  // active this switches to one page_size=100 fetch and filters client-side (see the note
  // rendered below the table).
  const pagedQuery = useQuery({
    queryKey: ["assets", "paged", page],
    queryFn: () => apiRequestWithMeta<Asset[]>("/assets", { params: { page, page_size: PAGE_SIZE } }),
    enabled: !isFiltered,
  });
  const filteredQuery = useQuery({
    queryKey: ["assets", "filtered"],
    queryFn: () => api.get<Asset[]>("/assets", { page: 1, page_size: FILTERED_PAGE_SIZE }),
    enabled: isFiltered,
  });

  const filteredAssets = useMemo(() => {
    if (!filteredQuery.data) return undefined;
    const q = search.trim().toLowerCase();
    return filteredQuery.data.filter((a) => {
      if (q && !a.name.toLowerCase().includes(q)) return false;
      if (typeId && a.asset_type_id !== typeId) return false;
      if (locationId && a.current_location_id !== locationId) return false;
      return true;
    });
  }, [filteredQuery.data, search, typeId, locationId]);

  const isLoading = isFiltered ? filteredQuery.isLoading : pagedQuery.isLoading;
  const isError = isFiltered ? filteredQuery.isError : pagedQuery.isError;
  const error = isFiltered ? filteredQuery.error : pagedQuery.error;
  const refetch = isFiltered ? filteredQuery.refetch : pagedQuery.refetch;
  const assets = isFiltered ? filteredAssets : pagedQuery.data?.data;

  function handleFilterChange(setter: (v: string) => void) {
    return (v: string) => {
      setter(v);
      setPage(1);
    };
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Assets</h1>
          <p className="text-sm text-slate-500 mt-1">The tenant's registered asset inventory.</p>
        </div>
        {canCreate && (
          <Link
            to="/assets/new"
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            New asset
          </Link>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[14rem]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by name…"
            value={search}
            onChange={(e) => handleFilterChange(setSearch)(e.target.value)}
            className="w-full rounded-md border border-slate-300 pl-9 pr-3 py-2 text-sm"
          />
        </div>
        <select value={typeId} onChange={(e) => handleFilterChange(setTypeId)(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
          <option value="">All types</option>
          {typesQuery.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <select value={locationId} onChange={(e) => handleFilterChange(setLocationId)(e.target.value)} className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
          <option value="">All locations</option>
          {locationsQuery.data?.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </div>

      {isFiltered && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          Showing matches from the first {FILTERED_PAGE_SIZE} assets only — search and filters aren't server-side yet.
        </p>
      )}

      {isLoading && <LoadingState />}
      {isError && <ErrorState message={apiErrorMessage(error, "Unable to load assets.")} onRetry={() => void refetch()} />}

      {assets && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Location</th>
                <th className="px-4 py-2 font-medium">Lifecycle state</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">
                    <Link to={`/assets/${a.id}`} className="text-[var(--accent)] hover:underline font-medium">
                      {a.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-600">{typesQuery.map.get(a.asset_type_id)?.name ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-600">{a.current_location_id ? (locationsQuery.map.get(a.current_location_id)?.name ?? "—") : "—"}</td>
                  <td className="px-4 py-2">
                    {a.current_lifecycle_state_id ? (
                      <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 text-xs px-2 py-0.5">
                        {statesQuery.map.get(a.current_lifecycle_state_id)?.label ?? "—"}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{new Date(a.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {assets.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState message={isFiltered ? "No assets match your filters." : "No assets yet."} />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!isFiltered && pagedQuery.data?.meta && (
        <Pagination page={pagedQuery.data.meta.page} pageSize={pagedQuery.data.meta.page_size} total={pagedQuery.data.meta.total} onPageChange={setPage} />
      )}
    </div>
  );
}
