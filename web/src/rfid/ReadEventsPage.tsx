import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { assetLabel, useAssetsLookup } from "../inventory/hooks";
import { deviceLabel, useDevicesLookup, useReadEvents } from "./hooks";
import type { ReadEventFilters } from "./types";

const PAGE_SIZE = 20;

/** Diagnostic, tenant-wide raw read-event feed. Filters are real server-side params, confirmed
 * directly against RfidReadEventRepository.list_filtered (track_rfid/repository.py:35-55):
 * resolved, device_id, tag_epc. There is deliberately NO date-range filter here — the backend
 * has no such param anywhere; read_at is only ever used to order the query, never to filter it
 * (the plan draft that preceded this page assumed one existed, but it doesn't, so this page
 * exposes device + resolved instead, both real). GET /rfid/read-events also returns no `total`
 * (plain array, same as GET /rfid/tags), so pagination is Prev/Next only — Next is disabled once
 * a page comes back shorter than the page size, since there's no count to know whether another
 * page exists ahead of time. */
export function ReadEventsPage() {
  const [deviceId, setDeviceId] = useState("");
  const [resolved, setResolved] = useState<"" | "true" | "false">("");
  const [offset, setOffset] = useState(0);

  const devicesLookup = useDevicesLookup();

  const filters: ReadEventFilters = {
    device_id: deviceId || undefined,
    resolved: resolved === "" ? undefined : resolved === "true",
    offset,
    limit: PAGE_SIZE,
  };
  const eventsQuery = useReadEvents(filters);

  const assetsLookup = useAssetsLookup((eventsQuery.data ?? []).filter((e) => e.asset_id).map((e) => e.asset_id as string));

  const devices = [...devicesLookup.map.values()].sort((a, b) => (a.vendor ?? a.device_type).localeCompare(b.vendor ?? b.device_type));
  const hasNextPage = (eventsQuery.data?.length ?? 0) === PAGE_SIZE;

  function updateFilter(fn: () => void) {
    fn();
    setOffset(0);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">RFID read events</h1>
        <p className="text-sm text-slate-500 mt-1">Raw reader pings ingested from device gateways, resolved or not, across the tenant.</p>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={deviceId}
          onChange={(e) => updateFilter(() => setDeviceId(e.target.value))}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
        >
          <option value="">All devices</option>
          {devices.map((d) => (
            <option key={d.id} value={d.id}>
              {[d.vendor, d.model].filter(Boolean).join(" ") || d.device_type}
            </option>
          ))}
        </select>
        <select
          value={resolved}
          onChange={(e) => updateFilter(() => setResolved(e.target.value as "" | "true" | "false"))}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white"
        >
          <option value="">All reads</option>
          <option value="true">Resolved</option>
          <option value="false">Unresolved</option>
        </select>
        {devices.length === 0 && (
          <p className="text-xs text-slate-400">Device names aren't available without gateway/device management access.</p>
        )}
      </div>

      {eventsQuery.isLoading && <LoadingState />}
      {eventsQuery.isError && (
        <ErrorState message={apiErrorMessage(eventsQuery.error, "Unable to load RFID read events.")} onRetry={() => void eventsQuery.refetch()} />
      )}

      {eventsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Read at</th>
                <th className="px-4 py-2 font-medium">Device</th>
                <th className="px-4 py-2 font-medium">EPC</th>
                <th className="px-4 py-2 font-medium">RSSI</th>
                <th className="px-4 py-2 font-medium">Asset</th>
              </tr>
            </thead>
            <tbody>
              {eventsQuery.data.map((e) => (
                <tr key={e.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2 text-slate-500">{new Date(e.read_at).toLocaleString()}</td>
                  <td className="px-4 py-2 text-slate-600">{deviceLabel(e.device_id, devicesLookup.map)}</td>
                  <td className="px-4 py-2 font-mono text-slate-900">{e.tag_epc}</td>
                  <td className="px-4 py-2 text-slate-600">{e.rssi ?? "—"}</td>
                  <td className="px-4 py-2">
                    {e.asset_id ? (
                      <Link to={`/assets/${e.asset_id}`} className="text-[var(--accent)] hover:underline">
                        {assetLabel(e.asset_id, assetsLookup.map)}
                      </Link>
                    ) : (
                      <span className="text-slate-400">Unresolved</span>
                    )}
                  </td>
                </tr>
              ))}
              {eventsQuery.data.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState message="No read events match your filters." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {eventsQuery.data && (offset > 0 || hasNextPage) && (
        <div className="flex items-center justify-between gap-3 text-sm text-slate-500 py-2">
          <span>{eventsQuery.data.length > 0 ? `Showing ${offset + 1}–${offset + eventsQuery.data.length}` : "No results"}</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={offset === 0}
              aria-label="Previous page"
              className="inline-flex items-center rounded-md border border-slate-300 p-1.5 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={!hasNextPage}
              aria-label="Next page"
              className="inline-flex items-center rounded-md border border-slate-300 p-1.5 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
