import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useDefinitions } from "./hooks";

export function DefinitionActiveBadge({ isActive }: { isActive: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${
        isActive ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"
      }`}
    >
      {isActive ? "active" : "inactive"}
    </span>
  );
}

/** GET /workflow/definitions/* requires only workflow.view (Viewer and Member both hold it,
 * per seed.py) — NOT Tenant-Admin-only end-to-end like RFID's GatewaysListPage. Only the "New"
 * link and, on DefinitionDetailPage, the mutation controls are gated workflow.manage_definitions
 * (Tenant-Admin-only). This page therefore renders for any workflow.view holder rather than
 * showing a whole-page permission message. */
export function DefinitionsListPage() {
  const { me } = useAuth();
  const canManageDefinitions = me?.permissions.includes("workflow.manage_definitions") ?? false;

  const [entityType, setEntityType] = useState("");
  const definitionsQuery = useDefinitions({ entity_type: entityType || undefined });

  // GET /workflow/definitions is server-ordered created_at asc — re-sorted by name here, more
  // useful for a small tenant-configured rule list than insertion order.
  const sorted = useMemo(
    () => [...(definitionsQuery.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [definitionsQuery.data],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Workflow definitions</h1>
          <p className="text-sm text-slate-500 mt-1">Approval-routing rules — which steps must approve which entities, and when.</p>
        </div>
        {canManageDefinitions && (
          <Link
            to="/workflow/definitions/new"
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            New definition
          </Link>
        )}
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <input
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          placeholder="Filter by entity type…"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm w-56"
        />
      </div>

      {definitionsQuery.isLoading && <LoadingState />}
      {definitionsQuery.isError && (
        <ErrorState message={apiErrorMessage(definitionsQuery.error, "Unable to load workflow definitions.")} onRetry={() => void definitionsQuery.refetch()} />
      )}

      {definitionsQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Entity type</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Condition</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">
                    <Link to={`/workflow/definitions/${d.id}`} className="text-[var(--accent)] hover:underline font-medium">
                      {d.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-600 font-mono text-xs">{d.entity_type}</td>
                  <td className="px-4 py-2">
                    <DefinitionActiveBadge isActive={d.is_active} />
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {d.condition_attribute ? (
                      <span className="font-mono text-xs">
                        {d.condition_attribute} {d.condition_operator} {JSON.stringify(d.condition_value)}
                      </span>
                    ) : (
                      "always"
                    )}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{new Date(d.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState message="No workflow definitions match your filters." />
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
