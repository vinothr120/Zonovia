import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { custodianLabel, useUsersLookup } from "../users/hooks";
import { TicketStatusBadge } from "./AssetTicketsSection";
import { assetLabel, useAssetsLookup, useTickets } from "./hooks";
import type { TicketStatus } from "./types";

const STATUS_OPTIONS: TicketStatus[] = ["open", "in_progress", "completed", "cancelled"];

/** GET /maintenance/tickets has real server-side filters (status, asset_id, assigned_to,
 * lifecycle_state_key) — unlike AssetListPage, no client-filter workaround is needed. Only
 * status and "assigned to me" are exposed as UI controls; asset_id is read from the URL
 * silently (set by AssetTicketsSection's "View all" link) with no visible filter chip, and
 * lifecycle_state_key isn't exposed this round. No server-side ordering, so results are
 * client-sorted by created_at desc. */
export function TicketsListPage() {
  const { me } = useAuth();
  const canManageTickets = me?.permissions.includes("maintenance.manage_tickets") ?? false;
  const [searchParams] = useSearchParams();
  const scopedAssetId = searchParams.get("asset_id") ?? undefined;

  const [status, setStatus] = useState<TicketStatus | "">("");
  const [assignedToMe, setAssignedToMe] = useState(false);

  const usersLookup = useUsersLookup();

  const ticketsQuery = useTickets({
    status: status || undefined,
    asset_id: scopedAssetId,
    assigned_to: assignedToMe ? (me?.id ?? undefined) : undefined,
  });

  const sorted = useMemo(
    () => [...(ticketsQuery.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [ticketsQuery.data],
  );
  const assetsLookup = useAssetsLookup(sorted.map((t) => t.asset_id));

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Maintenance tickets</h1>
          <p className="text-sm text-slate-500 mt-1">Repair and service requests across the tenant's assets.</p>
        </div>
        {canManageTickets && (
          <Link
            to="/maintenance/tickets/new"
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            New ticket
          </Link>
        )}
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <select value={status} onChange={(e) => setStatus(e.target.value as TicketStatus | "")} className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input type="checkbox" checked={assignedToMe} onChange={(e) => setAssignedToMe(e.target.checked)} />
          Assigned to me
        </label>
      </div>

      {ticketsQuery.isLoading && <LoadingState />}
      {ticketsQuery.isError && (
        <ErrorState message={apiErrorMessage(ticketsQuery.error, "Unable to load maintenance tickets.")} onRetry={() => void ticketsQuery.refetch()} />
      )}

      {ticketsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Title</th>
                <th className="px-4 py-2 font-medium">Asset</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Priority</th>
                <th className="px-4 py-2 font-medium">Assigned to</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((t) => (
                <tr key={t.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">
                    <Link to={`/maintenance/tickets/${t.id}`} className="text-[var(--accent)] hover:underline font-medium">
                      {t.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <Link to={`/assets/${t.asset_id}`} className="text-slate-600 hover:underline">
                      {assetLabel(t.asset_id, assetsLookup.map)}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <TicketStatusBadge status={t.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-600">{t.priority ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-600">{custodianLabel(t.assigned_to, usersLookup.map)}</td>
                  <td className="px-4 py-2 text-slate-500">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={6}>
                    <EmptyState message="No maintenance tickets match your filters." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
