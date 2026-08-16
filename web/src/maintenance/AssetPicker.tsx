import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../core/apiClient";
import type { Asset } from "../assets/types";

const FILTERED_PAGE_SIZE = 100;

/** Compact type-ahead over the tenant's asset registry, adapting AssetListPage's client-filter
 * pattern (GET /assets has no search param) into a single-select combobox for TicketFormPage's
 * tenant-wide entry point. Reuses the exact ["assets", "filtered"] query key AssetListPage's
 * filtered branch uses, so the two pages share one cached fetch. Same "first N assets only"
 * shortcoming as AssetListPage — acceptable here since this is a lookup, not a full listing. */
export function AssetPicker({ value, onChange }: { value: string; onChange: (assetId: string) => void }) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);

  const assetsQuery = useQuery({
    queryKey: ["assets", "filtered"],
    queryFn: () => api.get<Asset[]>("/assets", { page: 1, page_size: FILTERED_PAGE_SIZE }),
  });

  const selected = useMemo(() => assetsQuery.data?.find((a) => a.id === value), [assetsQuery.data, value]);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return (assetsQuery.data ?? []).filter((a) => a.name.toLowerCase().includes(q)).slice(0, 10);
  }, [assetsQuery.data, search]);

  if (value && selected) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border border-slate-300 px-3 py-2 text-sm bg-slate-50">
        <span className="text-slate-900">{selected.name}</span>
        <button type="button" onClick={() => onChange("")} className="text-xs text-[var(--accent)] hover:underline shrink-0">
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="relative">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search assets by name…"
          className="w-full rounded-md border border-slate-300 pl-9 pr-3 py-2 text-sm"
        />
      </div>
      {open && search.trim() !== "" && (
        <ul className="absolute z-10 mt-1 w-full max-h-56 overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg text-sm">
          {matches.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => {
                  onChange(a.id);
                  setSearch("");
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 hover:bg-slate-50"
              >
                {a.name}
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="px-3 py-2 text-slate-400">No matching assets.</li>}
        </ul>
      )}
    </div>
  );
}
