import { useState } from "react";
import { Link } from "react-router-dom";
import { PlayCircle } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { apiErrorMessage, EmptyState, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useInstances } from "./hooks";
import type { InstanceStatus, StepStatus } from "./types";

const INSTANCE_STATUSES: InstanceStatus[] = ["pending", "approved", "rejected", "cancelled"];

const INSTANCE_STATUS_STYLES: Record<InstanceStatus, string> = {
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-slate-100 text-slate-700",
};

export function InstanceStatusBadge({ status }: { status: InstanceStatus }) {
  return <span className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${INSTANCE_STATUS_STYLES[status]}`}>{status}</span>;
}

const STEP_STATUS_STYLES: Record<StepStatus, string> = {
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  skipped: "bg-slate-100 text-slate-700",
};

export function StepStatusBadge({ status }: { status: StepStatus }) {
  return <span className={`inline-flex items-center rounded-full text-xs px-2 py-0.5 ${STEP_STATUS_STYLES[status]}`}>{status}</span>;
}

/** Tenant-wide admin view — GET /workflow/instances requires only workflow.view, server-ordered
 * created_at desc (no client sort needed). entity_type/entity_id are free-text/no-FK by design
 * (see WorkflowDefinition's model docstring), so rows show them as plain text rather than
 * fabricating a link into a real business entity that may not correspond to any route in this
 * app. "Evaluate" is gated workflow.manage_definitions — POST /workflow/instances/evaluate is
 * conservatively gated the same as every mutation endpoint in this module (router.py's comment:
 * "a manual/administrative trigger... not the primary integration path"). */
export function InstancesListPage() {
  const { me } = useAuth();
  const canEvaluate = me?.permissions.includes("workflow.manage_definitions") ?? false;

  const [status, setStatus] = useState<InstanceStatus | "">("");
  const [entityType, setEntityType] = useState("");
  const instancesQuery = useInstances({ status: status || undefined, entity_type: entityType || undefined });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Approval instances</h1>
          <p className="text-sm text-slate-500 mt-1">Every open or resolved approval process across the tenant.</p>
        </div>
        {canEvaluate && (
          <Link
            to="/workflow/instances/evaluate"
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent)] text-white text-sm font-medium px-3.5 py-2 hover:bg-[var(--accent-dark)] transition-colors"
          >
            <PlayCircle className="w-4 h-4" />
            Evaluate entity
          </Link>
        )}
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <select value={status} onChange={(e) => setStatus(e.target.value as InstanceStatus | "")} className="rounded-md border border-slate-300 px-3 py-2 text-sm bg-white">
          <option value="">All statuses</option>
          {INSTANCE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          placeholder="Filter by entity type…"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm w-56"
        />
      </div>

      {instancesQuery.isLoading && <LoadingState />}
      {instancesQuery.isError && (
        <ErrorState message={apiErrorMessage(instancesQuery.error, "Unable to load approval instances.")} onRetry={() => void instancesQuery.refetch()} />
      )}

      {instancesQuery.data && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2 font-medium">Entity</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Current group</th>
                <th className="px-4 py-2 font-medium">Created</th>
                <th className="px-4 py-2 font-medium">Resolved</th>
              </tr>
            </thead>
            <tbody>
              {instancesQuery.data.map((i) => (
                <tr key={i.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">
                    <Link to={`/workflow/instances/${i.id}`} className="text-[var(--accent)] hover:underline font-medium">
                      {i.entity_type}
                    </Link>
                    <span className="block font-mono text-xs text-slate-400">{i.entity_id}</span>
                  </td>
                  <td className="px-4 py-2">
                    <InstanceStatusBadge status={i.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-600">{i.current_sequence_order ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-500">{new Date(i.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2 text-slate-500">{i.resolved_at ? new Date(i.resolved_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
              {instancesQuery.data.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState message="No approval instances match your filters." />
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
