import { Link } from "react-router-dom";
import { apiErrorMessage, ErrorState, LoadingState } from "../core/ui/StateViews";
import { useInstances } from "./hooks";
import { InstanceStatusBadge } from "./InstancesListPage";

/** Read-only, embedded on TicketDetailPage — the non-blocking Workflow integration's only UI
 * surface on the maintenance side. Queries GET /workflow/instances?entity_type=
 * maintenance_ticket&entity_id={ticketId} (already server-ordered created_at desc, so
 * data[0] is the most recent instance — no client sort needed, same convention as
 * InstancesListPage). Never renders a decision action itself; any Approve/Reject/Cancel
 * happens on the linked InstanceDetailPage. Gated on `canView` (computed by the caller from
 * workflow.view), same "always call the hook, gate the render" convention as
 * AssetTicketsSection's canView. */
export function TicketApprovalSection({ ticketId, canView }: { ticketId: string; canView: boolean }) {
  const instancesQuery = useInstances({ entity_type: "maintenance_ticket", entity_id: ticketId });

  if (!canView) {
    return (
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-700 mb-3">Approval</h2>
        <p className="text-sm text-slate-500">You don't have permission to view this ticket's approval status.</p>
      </div>
    );
  }

  const mostRecent = instancesQuery.data?.[0] ?? null;

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h2 className="text-sm font-medium text-slate-700 mb-3">Approval</h2>

      {instancesQuery.isLoading && <LoadingState />}
      {instancesQuery.isError && (
        <ErrorState
          message={apiErrorMessage(instancesQuery.error, "Unable to load approval status.")}
          onRetry={() => void instancesQuery.refetch()}
        />
      )}

      {instancesQuery.data &&
        (mostRecent ? (
          <div className="flex items-center gap-3 text-sm">
            <InstanceStatusBadge status={mostRecent.status} />
            <Link to={`/workflow/instances/${mostRecent.id}`} className="text-[var(--accent)] hover:underline">
              View approval details
            </Link>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No approval required.</p>
        ))}
    </div>
  );
}
