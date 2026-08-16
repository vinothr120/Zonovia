import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useTickets } from "./hooks";
import type { TicketStatus } from "./types";

const STATUS_STYLES: Record<TicketStatus, string> = {
  open: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  cancelled: "bg-red-100 text-red-700",
};

/** Shared by AssetTicketsSection, TicketsListPage, and TicketDetailPage — one status-color
 * mapping, not three. */
export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${STATUS_STYLES[status]}`}>{status.replace("_", " ")}</span>
  );
}

/** Read-only mini-list, no per-row actions — status changes and edits happen on
 * TicketDetailPage. "New ticket" (asset-scoped entry point, pre-fills ?asset_id=) is gated on
 * canManageTickets; "View all" (tenant-wide list, scoped via ?asset_id=) is always shown. */
export function AssetTicketsSection({ assetId, canView, canManageTickets }: { assetId: string; canView: boolean; canManageTickets: boolean }) {
  const ticketsQuery = useTickets({ asset_id: assetId });

  const sorted = useMemo(
    () => [...(ticketsQuery.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [ticketsQuery.data],
  );

  if (!canView) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Maintenance tickets</h2>
        <p className="text-sm text-slate-500">You don't have permission to view this asset's maintenance tickets.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="text-sm font-medium text-slate-700">Maintenance tickets</h2>
        <div className="flex items-center gap-3">
          {canManageTickets && (
            <Link
              to={`/maintenance/tickets/new?asset_id=${assetId}`}
              className="inline-flex items-center gap-1 text-xs border border-slate-300 text-slate-700 rounded-md px-2 py-1 hover:bg-slate-50"
            >
              <Plus className="w-3.5 h-3.5" /> New ticket
            </Link>
          )}
          <Link to={`/maintenance/tickets?asset_id=${assetId}`} className="text-xs text-[var(--accent)] hover:underline">
            View all
          </Link>
        </div>
      </div>

      {ticketsQuery.isLoading && <LoadingState />}
      {ticketsQuery.isError && (
        <ErrorState message={apiErrorMessage(ticketsQuery.error, "Unable to load maintenance tickets.")} onRetry={() => void ticketsQuery.refetch()} />
      )}

      {ticketsQuery.data && (
        <ul className="divide-y divide-slate-100">
          {sorted.slice(0, 5).map((t) => (
            <li key={t.id} className="py-2 flex items-center justify-between gap-3 text-sm">
              <Link to={`/maintenance/tickets/${t.id}`} className="text-[var(--accent)] hover:underline font-medium truncate">
                {t.title}
              </Link>
              <TicketStatusBadge status={t.status} />
            </li>
          ))}
          {sorted.length === 0 && <EmptyState message="No maintenance tickets yet." />}
        </ul>
      )}
    </div>
  );
}
