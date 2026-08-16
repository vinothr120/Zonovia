import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { Breadcrumb } from "../core/ui/Breadcrumb";
import { locationBreadcrumb, useAssetLocations } from "../locations/hooks";
import { useInventoryCycles } from "./hooks";
import type { InventoryCycleStatus } from "./types";

const STATUS_STYLES: Record<InventoryCycleStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  cancelled: "bg-red-100 text-red-700",
};

function StatusBadge({ status }: { status: InventoryCycleStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${STATUS_STYLES[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function CyclesListPage() {
  const { me } = useAuth();
  const canManageCycles = me?.permissions.includes("inventory.manage_cycles") ?? false;

  const cyclesQuery = useInventoryCycles();
  const locationsQuery = useAssetLocations();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Inventory cycles</h1>
          <p className="text-sm text-slate-500 mt-1">Periodic physical-verification exercises against the asset registry.</p>
        </div>
        {canManageCycles && (
          <Link
            to="/inventory/new"
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            New cycle
          </Link>
        )}
      </div>

      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
        Showing the most recent 20 cycles — this list isn't paginated yet.
      </p>

      {cyclesQuery.isLoading && <LoadingState />}
      {cyclesQuery.isError && (
        <ErrorState message={apiErrorMessage(cyclesQuery.error, "Unable to load inventory cycles.")} onRetry={() => void cyclesQuery.refetch()} />
      )}

      {cyclesQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Scope</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2 font-medium">Completed</th>
              </tr>
            </thead>
            <tbody>
              {cyclesQuery.data.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">
                    <Link to={`/inventory/${c.id}`} className="text-[var(--accent)] hover:underline font-medium">
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-2">
                    {c.root_location_id ? (
                      <Breadcrumb segments={locationBreadcrumb(c.root_location_id, locationsQuery.map)} />
                    ) : (
                      <span className="text-slate-600">Entire tenant</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{c.started_at ? new Date(c.started_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-2 text-slate-500">{c.completed_at ? new Date(c.completed_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
              {cyclesQuery.data.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState message="No inventory cycles yet." />
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
