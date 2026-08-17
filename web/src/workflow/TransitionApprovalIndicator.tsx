import { Link } from "react-router-dom";
import { useInstances } from "./hooks";
import { InstanceStatusBadge } from "./InstancesListPage";

/** Inline, read-only indicator for a single lifecycle transition's approval status — mirrors
 * TicketApprovalSection's shape but compact enough for a HistoryFeed row. Renders nothing while
 * loading, on error, or when no instance exists for this transition (the common case, since most
 * transitions won't match any configured WorkflowDefinition), consistent with a diagnostic
 * indicator that shouldn't add noise to every history row. Always calls the hook, gates the
 * render on `canView` — same convention as every other workflow.view-gated component. */
export function TransitionApprovalIndicator({ transitionId, canView }: { transitionId: string; canView: boolean }) {
  const instancesQuery = useInstances({ entity_type: "asset_lifecycle_transition", entity_id: transitionId });

  if (!canView) return null;
  const mostRecent = instancesQuery.data?.[0];
  if (!mostRecent) return null;

  return (
    <Link to={`/workflow/instances/${mostRecent.id}`} className="inline-flex items-center gap-1 ml-2 hover:underline">
      <InstanceStatusBadge status={mostRecent.status} />
    </Link>
  );
}
